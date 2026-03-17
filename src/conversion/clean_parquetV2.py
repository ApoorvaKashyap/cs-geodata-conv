# import duckdb
# import os
# from datetime import date, timedelta

# def process_folder_to_geoparquet(folder_path):
#     """
#     Process all parquet files in a folder and create a clean GeoParquet output.
    
#     Args:
#         folder_path: Path to folder containing parquet files
    
#     Returns:
#         Path to the output GeoParquet file
#     """
    
#     # Get folder name for output file
#     folder_name = os.path.basename(folder_path.rstrip('/\\'))
#     output_file = os.path.join(folder_path, f"{folder_name}_clean.parquet")
    
#     # Initialize DuckDB connection
#     con = duckdb.connect()
#     con.install_extension("spatial")
#     con.load_extension("spatial")
    
#     # Get all parquet files (excluding any existing output files)
#     files = [f for f in os.listdir(folder_path) 
#              if f.endswith('.parquet') and "clean" not in f and "final" not in f]
    
#     if not files:
#         raise ValueError(f"No parquet files found in {folder_path}")
    
#     print(f"Found {len(files)} parquet files to process")
    
#     # Step 1: Join all parquet files
#     print("Step 1/6: Joining parquet files...")
#     base_file = os.path.join(folder_path, files[0])
#     con.execute(f"CREATE TABLE joined_data AS SELECT * FROM read_parquet('{base_file}')")
    
#     for i, next_file in enumerate(files[1:], 1):
#         file_path = os.path.join(folder_path, next_file)
#         print(f"  Joining file {i}/{len(files)-1}: {next_file}")
#         con.execute(f"""
#             CREATE OR REPLACE TABLE joined_data AS 
#             SELECT t1.*, t2.* EXCLUDE (uid, geometry)
#             FROM joined_data t1
#             INNER JOIN read_parquet('{file_path}') t2 USING (uid)
#         """)
    
#     # Step 2: Reorder columns (geometry first, uid second)
#     print("Step 2/6: Reordering columns...")
#     con.execute("""
#         CREATE OR REPLACE TABLE joined_data AS 
#         SELECT geometry, uid, * EXCLUDE (geometry, uid) 
#         FROM joined_data
#     """)
    
#     # Helper function to get columns
#     def get_columns():
#         result = con.execute("SELECT column_name, column_type FROM (DESCRIBE joined_data)").fetchall()
#         return {col[0]: col[1] for col in result}
    
#     all_columns = get_columns()
    
#     # Step 3: Convert JSON string columns to STRUCT (for biweekly data)
#     print("Step 3/6: Converting JSON strings to STRUCT format...")
    
#     # Generate biweekly dates
#     start = date(2017, 7, 1)
#     end = date(2023, 9, 16)
#     delta = timedelta(days=14)
    
#     biweekly_dates = []
#     current = start
#     while current <= end:
#         biweekly_dates.append(str(current))
#         current += delta
    
#     # Check if biweekly date columns exist as VARCHAR/JSON
#     biweekly_cols_exist = any(d in all_columns and 'VARCHAR' in all_columns[d] for d in biweekly_dates)
    
#     if biweekly_cols_exist:
#         print("  Found biweekly JSON string columns, converting to STRUCT...")
#         struct_definition = "STRUCT(DeltaG DOUBLE, ET DOUBLE, Precipitation DOUBLE, RunOff DOUBLE, G DOUBLE)"
        
#         conversion_count = 0
#         for date_col in biweekly_dates:
#             if date_col in all_columns and 'VARCHAR' in all_columns[date_col]:
#                 try:
#                     con.execute(f"""
#                         ALTER TABLE joined_data
#                         ALTER "{date_col}" TYPE {struct_definition}""")
    
#     if biweekly_cols_exist:
#         print("  Found biweekly struct columns, transforming to MAP...")
#         metrics = ["DeltaG", "Precipitation", "ET", "RunOff", "G"]
        
#         # Build MAP columns
#         keys_sql = ", ".join([f"DATE '{d}'" for d in biweekly_dates])
#         map_clauses = []
#         for m in metrics:
#             values_sql = ", ".join([f'"{d}".{m}' for d in biweekly_dates])
#             map_clauses.append(f"MAP([{keys_sql}], [{values_sql}]) AS {m}_Fortnightly")
        
#         exclude_sql = ", ".join([f'"{d}"' for d in biweekly_dates])
        
#         con.execute(f"""
#             CREATE OR REPLACE TABLE joined_data AS
#             SELECT 
#                 * EXCLUDE ({exclude_sql}), 
#                 {', '.join(map_clauses)}
#             FROM joined_data
#         """)
#         print(f"  Created {len(metrics)} MAP columns for biweekly data")
#     else:
#         print("  Skipping - no biweekly struct columns found")
    
#     # Refresh column list
#     all_columns = get_columns()
    
#     # Step 5: Transform cropping intensity data to MAP columns (if exists)
#     print("Step 5/6: Converting cropping data to MAP columns...")
    
#     years = list(range(2017, 2024))
#     crop_metrics = [
#         'cropping_intensity',
#         'doubly_cropped_area',
#         'single_cropped_area',
#         'single_kharif_cropped_area',
#         'single_non_kharif_cropped_area',
#         'triply_cropped_area'
#     ]
    
#     # Check if any cropping columns exist
#     crop_cols_exist = any(f"{metric}_{year}" in all_columns 
#                           for metric in crop_metrics 
#                           for year in years)
    
#     if crop_cols_exist:
#         print("  Found cropping columns, transforming...")
#         map_clauses = []
#         exclude_cols = []
        
#         for metric in crop_metrics:
#             # Only process if at least one year column exists
#             if any(f"{metric}_{year}" in all_columns for year in years):
#                 keys_sql = ", ".join([f"'{year}'" for year in years])
#                 values_sql = ", ".join([f"{metric}_{year}" for year in years])
#                 map_clauses.append(f"MAP([{keys_sql}], [{values_sql}]) AS {metric}")
                
#                 for year in years:
#                     col_name = f"{metric}_{year}"
#                     if col_name in all_columns:
#                         exclude_cols.append(col_name)
        
#         if map_clauses:
#             exclude_sql = ", ".join(exclude_cols)
#             con.execute(f"""
#                 CREATE OR REPLACE TABLE joined_data AS
#                 SELECT 
#                     * EXCLUDE ({exclude_sql}),
#                     {', '.join(map_clauses)}
#                 FROM joined_data
#             """)
#             print(f"  Created {len(map_clauses)} MAP columns for cropping data")
#     else:
#         print("  Skipping - no cropping columns found")
    
#     # Refresh column list
#     all_columns = get_columns()
    
#     # Step 6: Transform annual JSON data to MAP columns (if exists)
#     print("Step 6/6: Converting annual data to MAP columns...")
    
#     annual_years = [
#         '2017_2018', '2018_2019', '2019_2020', '2020_2021',
#         '2021_2022', '2022_2023', '2023_2024', '2024_2025'
#     ]
    
#     # Check if annual columns exist
#     annual_cols_exist = any(year in all_columns for year in annual_years)
    
#     if annual_cols_exist:
#         print("  Found annual JSON columns, transforming...")
#         annual_metrics = ["DeltaG", "ET", "Precipitation", "RunOff", "WellDepth", "G"]
        
#         map_clauses = []
#         for metric in annual_metrics:
#             keys_sql = ", ".join([f"'{year}'" for year in annual_years])
#             values_sql = ", ".join([f"json_extract(\"{year}\", '$.{metric}')" for year in annual_years])
#             map_clauses.append(f"MAP([{keys_sql}], [{values_sql}]) AS {metric}_Annual")
        
#         exclude_sql = ", ".join([f'"{year}"' for year in annual_years])
        
#         con.execute(f"""
#             CREATE OR REPLACE TABLE joined_data AS
#             SELECT 
#                 * EXCLUDE ({exclude_sql}),
#                 {', '.join(map_clauses)}
#             FROM joined_data
#         """)
#         print(f"  Created {len(map_clauses)} MAP columns for annual data")
#     else:
#         print("  Skipping - no annual JSON columns found")
    
#     # Refresh column list
#     all_columns = get_columns()
    
#     # Step 7: Transform net change data to MAP column (if exists)
#     print("Step 7/7: Converting net change data to MAP column...")
    
#     net_columns = {
#         'Net2017_22': '2017-2022',
#         'Net2018_23': '2018-2023',
#         'Net2019_24': '2019-2024',
#         'Net2020_25': '2020-2025'
#     }
    
#     # Check if net columns exist
#     net_cols_exist = any(col in all_columns for col in net_columns.keys())
    
#     if net_cols_exist:
#         print("  Found net change columns, transforming...")
#         # Only include columns that actually exist
#         existing_net_cols = {k: v for k, v in net_columns.items() if k in all_columns}
        
#         keys_sql = ", ".join([f"'{year_range}'" for year_range in existing_net_cols.values()])
#         values_sql = ", ".join([f"{col}" for col in existing_net_cols.keys()])
#         net_map_clause = f"MAP([{keys_sql}], [{values_sql}]) AS NetChange"
#         exclude_sql = ", ".join(existing_net_cols.keys())
        
#         con.execute(f"""
#             CREATE OR REPLACE TABLE joined_data AS
#             SELECT 
#                 * EXCLUDE ({exclude_sql}),
#                 {net_map_clause}
#             FROM joined_data
#         """)
#         print(f"  Created NetChange MAP column with {len(existing_net_cols)} entries")
#     else:
#         print("  Skipping - no net change columns found")
    
#     # Final: Export to GeoParquet
#     print(f"\nExporting to {output_file}...")
#     con.execute(f"COPY joined_data TO '{output_file}' (FORMAT PARQUET)")
    
#     # Verify output
#     row_count = con.execute(f"SELECT COUNT(*) FROM read_parquet('{output_file}')").fetchone()[0]
#     col_count = len(con.execute(f"DESCRIBE SELECT * FROM read_parquet('{output_file}')").fetchall())
    
#     print(f"\n{'='*60}")
#     print(f"✓ Successfully created: {output_file}")
#     print(f"✓ Total rows: {row_count:,}")
#     print(f"✓ Total columns: {col_count}")
#     print(f"{'='*60}")
    
#     con.close()
#     return output_file


# # Usage
# if __name__ == "__main__":
#     folder_path = input("Enter the location: ").strip()
    
#     if not os.path.exists(folder_path):
#         print(f"Error: Folder '{folder_path}' does not exist")
#     else:
#         output = process_folder_to_geoparquet(folder_path)
#         print(f"\nDone! Output file: {output}")    
#     # Check if biweekly struct columns exist
#     biweekly_cols_exist = any(d in all_columns and 'STRUCT' in all_columns[d] for d in biweekly_dates)
#                         USING "{date_col}"::JSON::{struct_definition};
#     else:
#     print("Step 4/6: Converting biweekly data to MAP columns...")
#     all_columns = get_columns()
    
#     # Step 4: Transform biweekly STRUCT data to MAP columns
#         print("  Skipping - no biweekly JSON string columns found")
    
#     # Refresh column list after conversion
#                     print(f"  Warning: Could not convert {date_col}: {e}")
        
#         print(f"""Converted {conversion_count} columns to STRUCT format")
#                     """)
#                     conversion_count += 1
#                 except Exception as e:

import re
import duckdb
import os

def process_folder_to_geoparquet(folder_path):
    """
    Process all JSON/GeoJSON files in a folder, merge them on uid,
    and output a flat-structure GeoParquet file.

    Flat column naming conventions:
      - Fortnightly : df_<YYYY-MM-DD>_<Metric>   e.g. df_2018-06-16_Precipitation
      - Annual      : dw_<YYYY_YYYY>_<Metric>    e.g. dw_2017_2018_DeltaG
      - Net Change  : dw_Net2017_22, dw_Net2018_23, ...
      - Cropping    : ci_<metric>_<year>          e.g. ci_cropping_intensity_2017

    Args:
        folder_path: Path to folder containing JSON/GeoJSON files

    Returns:
        Path to the output GeoParquet file
    """

    folder_name = os.path.basename(folder_path.rstrip('/\\'))

    # Create output subfolder: <input_folder>/parquet/
    output_dir = os.path.join(folder_path, "parquet")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{folder_name}_clean.parquet")

    # Initialize DuckDB with spatial extension
    con = duckdb.connect()
    con.install_extension("spatial")
    con.load_extension("spatial")

    # Discover all JSON / GeoJSON files (exclude the output folder)
    files = [
        f for f in os.listdir(folder_path)
        if f.lower().endswith(('.json', '.geojson'))
    ]

    if not files:
        raise ValueError(f"No JSON/GeoJSON files found in {folder_path}")

    print(f"Found {len(files)} JSON files to process")

    # ------------------------------------------------------------------ #
    # Step 1: Load and JOIN all files on uid                              #
    # ------------------------------------------------------------------ #
    print("Step 1/6: Loading and joining JSON files on uid...")

    first_path = os.path.join(folder_path, files[0]).replace("\\", "/")
    con.execute(f"CREATE TABLE joined_data AS SELECT * FROM ST_Read('{first_path}')")
    print(f"  Loaded base file: {files[0]}")

    for i, fname in enumerate(files[1:], 1):
        file_path = os.path.join(folder_path, fname).replace("\\", "/")
        print(f"  Joining file {i}/{len(files)-1}: {fname}")

        current_cols = set(
            r[0] for r in con.execute(
                "SELECT column_name FROM (DESCRIBE joined_data)"
            ).fetchall()
        )
        incoming_cols = set(
            r[0] for r in con.execute(
                f"SELECT column_name FROM (DESCRIBE SELECT * FROM ST_Read('{file_path}'))"
            ).fetchall()
        )

        new_cols = incoming_cols - current_cols - {'uid'}
        if not new_cols:
            print(f"    Skipping {fname} — no new columns to add")
            continue

        new_cols_sql = ", ".join([f't2."{c}"' for c in sorted(new_cols)])
        con.execute(f"""
            CREATE OR REPLACE TABLE joined_data AS
            SELECT t1.*, {new_cols_sql}
            FROM joined_data t1
            INNER JOIN ST_Read('{file_path}') t2
            ON t1.uid = t2.uid
        """)

    print(f"  All files joined successfully")

    # Helper
    def get_columns():
        result = con.execute(
            "SELECT column_name, column_type FROM (DESCRIBE joined_data)"
        ).fetchall()
        return {col[0]: col[1] for col in result}

    # ------------------------------------------------------------------ #
    # Step 2: Reorder columns — geometry first, uid second               #
    # ------------------------------------------------------------------ #
    print("Step 2/6: Reordering columns...")

    all_columns = get_columns()
    geom_col = 'geom' if 'geom' in all_columns else 'geometry'
    has_uid  = 'uid' in all_columns
    has_geom = geom_col in all_columns

    if has_geom and has_uid:
        con.execute(f"""
            CREATE OR REPLACE TABLE joined_data AS
            SELECT {geom_col} AS geometry, uid, * EXCLUDE ({geom_col}, uid)
            FROM joined_data
        """)
    elif has_geom:
        con.execute(f"""
            CREATE OR REPLACE TABLE joined_data AS
            SELECT {geom_col} AS geometry, * EXCLUDE ({geom_col})
            FROM joined_data
        """)
    else:
        print("  Warning: No geometry column detected — skipping reorder")

    all_columns = get_columns()

    # ------------------------------------------------------------------ #
    # Step 3: Fortnightly data → flat df_<date>_<Metric> columns         #
    # Source columns are date-named STRUCTs or VARCHAR JSON blobs        #
    # ------------------------------------------------------------------ #
    print("Step 3/6: Flattening fortnightly data → df_<date>_<Metric> columns...")

    metrics_fortnight = ["DeltaG", "ET", "Precipitation", "RunOff", "G"]

    # Dynamically detect ALL date-like columns (YYYY-MM-DD) in the actual table
    # This catches any dates outside the previously hardcoded range
    date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')

    struct_dates  = sorted([c for c, t in all_columns.items() if date_pattern.match(c) and 'STRUCT'  in t])
    varchar_dates = sorted([c for c, t in all_columns.items() if date_pattern.match(c) and 'VARCHAR' in t])

    if struct_dates:
        print(f"  Found {len(struct_dates)} STRUCT fortnightly columns, extracting flat...")
        flat_clauses = []
        for d in struct_dates:
            for m in metrics_fortnight:
                flat_clauses.append(f'("{d}").{m} AS "df_{d}_{m}"')
        exclude_sql = ", ".join([f'"{d}"' for d in struct_dates])
        con.execute(f"""
            CREATE OR REPLACE TABLE joined_data AS
            SELECT
                * EXCLUDE ({exclude_sql}),
                {', '.join(flat_clauses)}
            FROM joined_data
        """)
        print(f"  Created {len(flat_clauses)} flat columns, dropped {len(struct_dates)} source columns")

    elif varchar_dates:
        print(f"  Found {len(varchar_dates)} VARCHAR/JSON fortnightly columns, extracting flat...")
        flat_clauses = []
        for d in varchar_dates:
            for m in metrics_fortnight:
                flat_clauses.append(
                    f"CAST(json_extract(\"{d}\", '$.{m}') AS DOUBLE) AS \"df_{d}_{m}\""
                )
        exclude_sql = ", ".join([f'"{d}"' for d in varchar_dates])
        con.execute(f"""
            CREATE OR REPLACE TABLE joined_data AS
            SELECT
                * EXCLUDE ({exclude_sql}),
                {', '.join(flat_clauses)}
            FROM joined_data
        """)
        print(f"  Created {len(flat_clauses)} flat columns, dropped {len(varchar_dates)} source columns")

    else:
        print("  Skipping - no fortnightly columns found")

    all_columns = get_columns()

    # ------------------------------------------------------------------ #
    # Step 4: Annual data → flat dw_<year_range>_<Metric> columns        #
    # Net change → flat dw_Net<range> columns                            #
    # ------------------------------------------------------------------ #
    print("Step 4/6: Flattening annual data → dw_<year_range>_<Metric> columns...")

    annual_year_ranges = [
        '2017_2018', '2018_2019', '2019_2020', '2020_2021',
        '2021_2022', '2022_2023', '2023_2024', '2024_2025'
    ]
    metrics_annual = ["DeltaG", "ET", "Precipitation", "RunOff", "WellDepth", "G"]

    annual_cols_exist = any(yr in all_columns for yr in annual_year_ranges)

    if annual_cols_exist:
        print("  Found annual JSON columns, extracting flat...")
        flat_clauses = []
        existing_annual = [yr for yr in annual_year_ranges if yr in all_columns]
        for yr in existing_annual:
            for m in metrics_annual:
                flat_clauses.append(
                    f"CAST(json_extract(\"{yr}\", '$.{m}') AS DOUBLE) AS \"dw_{yr}_{m}\""
                )
        exclude_sql = ", ".join([f'"{yr}"' for yr in existing_annual])
        con.execute(f"""
            CREATE OR REPLACE TABLE joined_data AS
            SELECT
                * EXCLUDE ({exclude_sql}),
                {', '.join(flat_clauses)}
            FROM joined_data
        """)
        print(f"  Created {len(flat_clauses)} flat columns, dropped {len(existing_annual)} source columns")
    else:
        print("  Skipping - no annual JSON columns found")

    all_columns = get_columns()

    # Net change columns: rename Net2017_22 → dw_Net2017_22
    print("  Renaming net change columns → dw_Net<range>...")
    net_columns = {
        'Net2017_22': 'dw_Net2017_22',
        'Net2018_23': 'dw_Net2018_23',
        'Net2019_24': 'dw_Net2019_24',
        'Net2020_25': 'dw_Net2020_25',
    }
    existing_net = {src: dst for src, dst in net_columns.items() if src in all_columns}

    if existing_net:
        rename_clauses = [f'"{src}" AS "{dst}"' for src, dst in existing_net.items()]
        exclude_sql = ", ".join([f'"{src}"' for src in existing_net])
        con.execute(f"""
            CREATE OR REPLACE TABLE joined_data AS
            SELECT
                * EXCLUDE ({exclude_sql}),
                {', '.join(rename_clauses)}
            FROM joined_data
        """)
        print(f"  Renamed {len(existing_net)} net change columns (source columns dropped)")
    else:
        print("  Skipping - no net change columns found")

    all_columns = get_columns()

    # ------------------------------------------------------------------ #
    # Step 5: Cropping data → flat ci_<metric>_<year> columns            #
    # Source columns named <metric>_<year>; rename to ci_<metric>_<year> #
    # ------------------------------------------------------------------ #
    print("Step 5/6: Renaming cropping columns → ci_<metric>_<year>...")

    years = list(range(2017, 2025))
    crop_metrics = [
        'cropping_intensity',
        'doubly_cropped_area',
        'single_cropped_area',
        'single_kharif_cropped_area',
        'single_non_kharif_cropped_area',
        'triply_cropped_area'
    ]

    rename_clauses = []
    exclude_cols   = []

    for metric in crop_metrics:
        for year in years:
            src = f"{metric}_{year}"
            dst = f"ci_{metric}_{year}"
            if src in all_columns and dst not in all_columns:
                rename_clauses.append(f'"{src}" AS "{dst}"')
                exclude_cols.append(f'"{src}"')

    if rename_clauses:
        exclude_sql = ", ".join(exclude_cols)
        con.execute(f"""
            CREATE OR REPLACE TABLE joined_data AS
            SELECT
                * EXCLUDE ({exclude_sql}),
                {', '.join(rename_clauses)}
            FROM joined_data
        """)
        print(f"  Renamed {len(rename_clauses)} cropping columns (source columns dropped)")
    else:
        print("  Skipping - no unprefixed cropping columns found (may already be prefixed)")

    all_columns = get_columns()

    # ------------------------------------------------------------------ #
    # Step 6: Export to GeoParquet                                        #
    # ------------------------------------------------------------------ #
    print(f"\nStep 6/6: Exporting to {output_file}...")
    con.execute(f"COPY joined_data TO '{output_file}' (FORMAT PARQUET)")

    row_count = con.execute(
        f"SELECT COUNT(*) FROM read_parquet('{output_file}')"
    ).fetchone()[0]
    col_count = len(con.execute(
        f"DESCRIBE SELECT * FROM read_parquet('{output_file}')"
    ).fetchall())

    print(f"\n{'='*60}")
    print(f"✓ Successfully created: {output_file}")
    print(f"✓ Total rows: {row_count:,}")
    print(f"✓ Total columns: {col_count}")
    print(f"{'='*60}")

    con.close()
    return output_file


# Usage
if __name__ == "__main__":
    folder_path = input("Enter the folder path containing JSON files: ").strip()

    if not os.path.exists(folder_path):
        print(f"Error: Folder '{folder_path}' does not exist")
    else:
        output = process_folder_to_geoparquet(folder_path)
        print(f"\nDone! Output file: {output}")
