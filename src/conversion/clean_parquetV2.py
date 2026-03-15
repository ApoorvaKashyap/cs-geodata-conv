import duckdb
import os
from datetime import date, timedelta

def process_folder_to_geoparquet(folder_path):
    """
    Process all parquet files in a folder and create a clean GeoParquet output.
    
    Args:
        folder_path: Path to folder containing parquet files
    
    Returns:
        Path to the output GeoParquet file
    """
    
    # Get folder name for output file
    folder_name = os.path.basename(folder_path.rstrip('/\\'))
    output_file = os.path.join(folder_path, f"{folder_name}_clean.parquet")
    
    # Initialize DuckDB connection
    con = duckdb.connect()
    con.install_extension("spatial")
    con.load_extension("spatial")
    
    # Get all parquet files (excluding any existing output files)
    files = [f for f in os.listdir(folder_path) 
             if f.endswith('.parquet') and "clean" not in f and "final" not in f]
    
    if not files:
        raise ValueError(f"No parquet files found in {folder_path}")
    
    print(f"Found {len(files)} parquet files to process")
    
    # Step 1: Join all parquet files
    print("Step 1/6: Joining parquet files...")
    base_file = os.path.join(folder_path, files[0])
    con.execute(f"CREATE TABLE joined_data AS SELECT * FROM read_parquet('{base_file}')")
    
    for i, next_file in enumerate(files[1:], 1):
        file_path = os.path.join(folder_path, next_file)
        print(f"  Joining file {i}/{len(files)-1}: {next_file}")
        con.execute(f"""
            CREATE OR REPLACE TABLE joined_data AS 
            SELECT t1.*, t2.* EXCLUDE (uid, geometry)
            FROM joined_data t1
            INNER JOIN read_parquet('{file_path}') t2 USING (uid)
        """)
    
    # Step 2: Reorder columns (geometry first, uid second)
    print("Step 2/6: Reordering columns...")
    con.execute("""
        CREATE OR REPLACE TABLE joined_data AS 
        SELECT geometry, uid, * EXCLUDE (geometry, uid) 
        FROM joined_data
    """)
    
    # Helper function to get columns
    def get_columns():
        result = con.execute("SELECT column_name, column_type FROM (DESCRIBE joined_data)").fetchall()
        return {col[0]: col[1] for col in result}
    
    all_columns = get_columns()
    
    # Step 3: Convert JSON string columns to STRUCT (for biweekly data)
    print("Step 3/6: Converting JSON strings to STRUCT format...")
    
    # Generate biweekly dates
    start = date(2017, 7, 1)
    end = date(2023, 9, 16)
    delta = timedelta(days=14)
    
    biweekly_dates = []
    current = start
    while current <= end:
        biweekly_dates.append(str(current))
        current += delta
    
    # Check if biweekly date columns exist as VARCHAR/JSON
    biweekly_cols_exist = any(d in all_columns and 'VARCHAR' in all_columns[d] for d in biweekly_dates)
    
    if biweekly_cols_exist:
        print("  Found biweekly JSON string columns, converting to STRUCT...")
        struct_definition = "STRUCT(DeltaG DOUBLE, ET DOUBLE, Precipitation DOUBLE, RunOff DOUBLE, G DOUBLE)"
        
        conversion_count = 0
        for date_col in biweekly_dates:
            if date_col in all_columns and 'VARCHAR' in all_columns[date_col]:
                try:
                    con.execute(f"""
                        ALTER TABLE joined_data
                        ALTER "{date_col}" TYPE {struct_definition}
    
    if biweekly_cols_exist:
        print("  Found biweekly struct columns, transforming to MAP...")
        metrics = ["DeltaG", "Precipitation", "ET", "RunOff", "G"]
        
        # Build MAP columns
        keys_sql = ", ".join([f"DATE '{d}'" for d in biweekly_dates])
        map_clauses = []
        for m in metrics:
            values_sql = ", ".join([f'"{d}".{m}' for d in biweekly_dates])
            map_clauses.append(f"MAP([{keys_sql}], [{values_sql}]) AS {m}_Fortnightly")
        
        exclude_sql = ", ".join([f'"{d}"' for d in biweekly_dates])
        
        con.execute(f"""
            CREATE OR REPLACE TABLE joined_data AS
            SELECT 
                * EXCLUDE ({exclude_sql}), 
                {', '.join(map_clauses)}
            FROM joined_data
        """)
        print(f"  Created {len(metrics)} MAP columns for biweekly data")
    else:
        print("  Skipping - no biweekly struct columns found")
    
    # Refresh column list
    all_columns = get_columns()
    
    # Step 5: Transform cropping intensity data to MAP columns (if exists)
    print("Step 5/6: Converting cropping data to MAP columns...")
    
    years = list(range(2017, 2024))
    crop_metrics = [
        'cropping_intensity',
        'doubly_cropped_area',
        'single_cropped_area',
        'single_kharif_cropped_area',
        'single_non_kharif_cropped_area',
        'triply_cropped_area'
    ]
    
    # Check if any cropping columns exist
    crop_cols_exist = any(f"{metric}_{year}" in all_columns 
                          for metric in crop_metrics 
                          for year in years)
    
    if crop_cols_exist:
        print("  Found cropping columns, transforming...")
        map_clauses = []
        exclude_cols = []
        
        for metric in crop_metrics:
            # Only process if at least one year column exists
            if any(f"{metric}_{year}" in all_columns for year in years):
                keys_sql = ", ".join([f"'{year}'" for year in years])
                values_sql = ", ".join([f"{metric}_{year}" for year in years])
                map_clauses.append(f"MAP([{keys_sql}], [{values_sql}]) AS {metric}")
                
                for year in years:
                    col_name = f"{metric}_{year}"
                    if col_name in all_columns:
                        exclude_cols.append(col_name)
        
        if map_clauses:
            exclude_sql = ", ".join(exclude_cols)
            con.execute(f"""
                CREATE OR REPLACE TABLE joined_data AS
                SELECT 
                    * EXCLUDE ({exclude_sql}),
                    {', '.join(map_clauses)}
                FROM joined_data
            """)
            print(f"  Created {len(map_clauses)} MAP columns for cropping data")
    else:
        print("  Skipping - no cropping columns found")
    
    # Refresh column list
    all_columns = get_columns()
    
    # Step 6: Transform annual JSON data to MAP columns (if exists)
    print("Step 6/6: Converting annual data to MAP columns...")
    
    annual_years = [
        '2017_2018', '2018_2019', '2019_2020', '2020_2021',
        '2021_2022', '2022_2023', '2023_2024', '2024_2025'
    ]
    
    # Check if annual columns exist
    annual_cols_exist = any(year in all_columns for year in annual_years)
    
    if annual_cols_exist:
        print("  Found annual JSON columns, transforming...")
        annual_metrics = ["DeltaG", "ET", "Precipitation", "RunOff", "WellDepth", "G"]
        
        map_clauses = []
        for metric in annual_metrics:
            keys_sql = ", ".join([f"'{year}'" for year in annual_years])
            values_sql = ", ".join([f"json_extract(\"{year}\", '$.{metric}')" for year in annual_years])
            map_clauses.append(f"MAP([{keys_sql}], [{values_sql}]) AS {metric}_Annual")
        
        exclude_sql = ", ".join([f'"{year}"' for year in annual_years])
        
        con.execute(f"""
            CREATE OR REPLACE TABLE joined_data AS
            SELECT 
                * EXCLUDE ({exclude_sql}),
                {', '.join(map_clauses)}
            FROM joined_data
        """)
        print(f"  Created {len(map_clauses)} MAP columns for annual data")
    else:
        print("  Skipping - no annual JSON columns found")
    
    # Refresh column list
    all_columns = get_columns()
    
    # Step 7: Transform net change data to MAP column (if exists)
    print("Step 7/7: Converting net change data to MAP column...")
    
    net_columns = {
        'Net2017_22': '2017-2022',
        'Net2018_23': '2018-2023',
        'Net2019_24': '2019-2024',
        'Net2020_25': '2020-2025'
    }
    
    # Check if net columns exist
    net_cols_exist = any(col in all_columns for col in net_columns.keys())
    
    if net_cols_exist:
        print("  Found net change columns, transforming...")
        # Only include columns that actually exist
        existing_net_cols = {k: v for k, v in net_columns.items() if k in all_columns}
        
        keys_sql = ", ".join([f"'{year_range}'" for year_range in existing_net_cols.values()])
        values_sql = ", ".join([f"{col}" for col in existing_net_cols.keys()])
        net_map_clause = f"MAP([{keys_sql}], [{values_sql}]) AS NetChange"
        exclude_sql = ", ".join(existing_net_cols.keys())
        
        con.execute(f"""
            CREATE OR REPLACE TABLE joined_data AS
            SELECT 
                * EXCLUDE ({exclude_sql}),
                {net_map_clause}
            FROM joined_data
        """)
        print(f"  Created NetChange MAP column with {len(existing_net_cols)} entries")
    else:
        print("  Skipping - no net change columns found")
    
    # Final: Export to GeoParquet
    print(f"\nExporting to {output_file}...")
    con.execute(f"COPY joined_data TO '{output_file}' (FORMAT PARQUET)")
    
    # Verify output
    row_count = con.execute(f"SELECT COUNT(*) FROM read_parquet('{output_file}')").fetchone()[0]
    col_count = len(con.execute(f"DESCRIBE SELECT * FROM read_parquet('{output_file}')").fetchall())
    
    print(f"\n{'='*60}")
    print(f"✓ Successfully created: {output_file}")
    print(f"✓ Total rows: {row_count:,}")
    print(f"✓ Total columns: {col_count}")
    print(f"{'='*60}")
    
    con.close()
    return output_file


# Usage
if __name__ == "__main__":
    folder_path = input("Enter the location: ").strip()
    
    if not os.path.exists(folder_path):
        print(f"Error: Folder '{folder_path}' does not exist")
    else:
        output = process_folder_to_geoparquet(folder_path)
        print(f"\nDone! Output file: {output}")    
    # Check if biweekly struct columns exist
    biweekly_cols_exist = any(d in all_columns and 'STRUCT' in all_columns[d] for d in biweekly_dates)
                        USING "{date_col}"::JSON::{struct_definition};
    else:
    print("Step 4/6: Converting biweekly data to MAP columns...")
    all_columns = get_columns()
    
    # Step 4: Transform biweekly STRUCT data to MAP columns
        print("  Skipping - no biweekly JSON string columns found")
    
    # Refresh column list after conversion
                    print(f"  Warning: Could not convert {date_col}: {e}")
        
        print(f"  Converted {conversion_count} columns to STRUCT format")
                    """)
                    conversion_count += 1
                except Exception as e:

