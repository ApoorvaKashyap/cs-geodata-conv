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
    print("Step 1/7: Loading and joining JSON files on uid...")

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
    print("Step 2/7: Reordering columns...")

    all_columns = get_columns()
    geom_col = 'geom' if 'geom' in all_columns else 'geometry'
    has_uid  = 'uid' in all_columns
    has_geom = geom_col in all_columns

    if has_geom and has_uid:
        con.execute(f"""
            CREATE OR REPLACE TABLE joined_data AS
            SELECT {geom_col} AS geometry, uid AS mwsid, * EXCLUDE ({geom_col}, uid)
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
    print("Step 3/7: Flattening fortnightly data → df_<date>_<Metric> columns...")

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
    print("Step 4/7: Flattening annual data → dw_<year_range>_<Metric> columns...")

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
    print("Step 5/7: Renaming cropping columns → ci_<metric>_<year>...")

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
    # Step 6: Column cleanup — rename, drop, split per schema             #
    # ------------------------------------------------------------------ #
    print("Step 6/7: Applying column schema (rename / drop / split)...")

    all_columns = get_columns()

    # ---- 1. DROP columns ----------------------------------------------
    # Each entry lists possible names (prefixed and bare) — drops whichever exist
    cols_to_drop = [c for c in [
        'aq_id', 'id',
        'aq_newcode43', 'newcode43',
        'aq_aquifer_class', 'aquifer_class',
        'aq_test', 'test',
        'aq_weighted_a', 'weighted_a',
        'aq_area_in_ha_1', 'area_in_ha_1',
        'aq_area_in_ha_2', 'area_in_ha_2',
        'aq_area_in_ha_3', 'area_in_ha_3',
        'aq_area_in_ha_4', 'area_in_ha_4',
        'aq_area_in_ha_5', 'area_in_ha_5',
        'sg_soge_state', 'soge_state',
    ] if c in all_columns]

    if cols_to_drop:
        drop_sql = ', '.join(['"' + c + '"' for c in cols_to_drop])
        con.execute("CREATE OR REPLACE TABLE joined_data AS SELECT * EXCLUDE (" + drop_sql + ") FROM joined_data")
        print(f"  Dropped {len(cols_to_drop)} columns")
    all_columns = get_columns()

    # ---- 2. SPLIT / TRANSFORM columns ---------------------------------
    # Each block tries prefixed name first, then bare name
    split_ops = []
    drop_after = []

    for src in ['aq_avg_mbgl', 'avg_mbgl']:
        if src in all_columns:
            s = '"' + src + '"'
            norm = "REGEXP_REPLACE(" + s + ", '[ ]*to[ ]*', '-')"
            split_ops += [
                (src, "CAST(TRIM(SPLIT_PART(" + norm + ",'-',1)) AS FLOAT)", 'aq_avg_mbgl_min'),
                (src, "CAST(TRIM(SPLIT_PART(" + norm + ",'-',2)) AS FLOAT)", 'aq_avg_mbgl_max'),
            ]
            drop_after.append(src); break

    for src in ['aq_m2_perday', 'm2_perday']:
        if src in all_columns:
            s = '"' + src + '"'
            split_ops.append((src, "CAST(REGEXP_REPLACE(" + s + ", '(?i)up[ ]*to[ ]*', '') AS FLOAT)", 'aq_m2_per_day_max'))
            drop_after.append(src); break

    for src in ['aq_m3_per_day', 'm3_per_day']:
        if src in all_columns:
            s = '"' + src + '"'
            norm = "REGEXP_REPLACE(" + s + ", '[ ]*to[ ]*', '-')"
            split_ops += [
                (src, "CAST(TRIM(SPLIT_PART(" + norm + ",'-',1)) AS FLOAT)", 'aq_m3_per_day_min'),
                (src, "CAST(TRIM(SPLIT_PART(" + norm + ",'-',2)) AS FLOAT)", 'aq_m3_per_day_max'),
            ]
            drop_after.append(src); break

    for src in ['aq_mbgl', 'mbgl']:
        if src in all_columns:
            s = '"' + src + '"'
            norm = "REGEXP_REPLACE(" + s + ", '[ ]*-[ ]*', '-')"
            split_ops += [
                (src, "CAST(TRIM(SPLIT_PART(" + norm + ",'-',1)) AS FLOAT)", 'aq_mbgl_min'),
                (src, "CAST(TRIM(SPLIT_PART(" + norm + ",'-',2)) AS FLOAT)", 'aq_mbgl_max'),
            ]
            drop_after.append(src); break

    for src in ['aq_yeild__', 'yeild__']:
        if src in all_columns:
            s = '"' + src + '"'
            norm = "REGEXP_REPLACE(REPLACE(" + s + ", '%', ''), '[ ]*-[ ]*', '-')"
            split_ops += [
                (src, "CAST(TRIM(SPLIT_PART(" + norm + ",'-',1)) AS FLOAT)", 'aq_yield_min'),
                (src, "CAST(TRIM(SPLIT_PART(" + norm + ",'-',2)) AS FLOAT)", 'aq_yield_max'),
            ]
            drop_after.append(src); break

    for src in ['aq_zone_m', 'zone_m']:
        if src in all_columns and src != 'aq_zone_m':
            split_ops.append((src, '"' + src + '"', 'aq_zone_m'))
            drop_after.append(src); break

    if split_ops:
        new_cols = ', '.join([expr + ' AS "' + nm + '"' for _, expr, nm in split_ops])
        seen = list(dict.fromkeys(drop_after))
        drop_sql = ', '.join(['"' + c + '"' for c in seen if c in all_columns])
        excl = ('* EXCLUDE (' + drop_sql + ')') if drop_sql else '*'
        con.execute("CREATE OR REPLACE TABLE joined_data AS SELECT " + excl + ", " + new_cols + " FROM joined_data")
        print(f"  Created {len(split_ops)} split/transform columns, dropped {len(seen)} originals")
    all_columns = get_columns()

    # ---- 3. SIMPLE RENAMES --------------------------------------------
    # Each tuple: (possible_bare_name, possible_prefixed_name, final_name)
    # Script picks whichever variant exists in the table
    rename_candidates = [
        (['%_area_aquifer',   'aq_%_area_aquifer'],   'aq_pct_area_aquifer'),
        (['Age',              'aq_Age'],               'aq_age'),
        (['Lithology_',       'aq_Lithology_'],        'aq_litho_type_code'),
        (['Major_Aq_1',       'aq_Major_Aq_1'],        'aq_aqui_type_code'),
        (['Major_Aqui',       'aq_Major_Aqui'],        'aq_aqui_type'),
        (['Principal_',       'aq_Principal_'],        'aq_principal_soil'),
        (['Recommende',       'aq_Recommende'],        'aq_rec_interventions'),
        (['aquifer_count',    'aq_aquifer_count'],     'aq_aqui_count'),
        (['newcode14',        'aq_newcode14'],         'aq_aqui_code14'),
        (['area_in_ha',       'aq_area_in_ha'],        'aq_area_in_ha'),
        (['area_re',          'aq_area_re'],           'aq_area_re'),
        (['intersection_area_ha', 'aq_intersection_area_ha'], 'aq_intersection_area_ha'),
        (['objectid',         'aq_objectid'],          'aq_objectid'),
        (['pa_order',         'aq_pa_order'],          'aq_pa_order'),
        (['per_cm',           'aq_per_cm'],            'aq_per_cm'),
        (['state',            'aq_state'],             'aq_state'),
        (['system',           'aq_system'],            'aq_system'),
        (['weighted_contribution', 'aq_weighted_contribution'], 'aq_weighted_contribution'),
        (['y_value',          'aq_y_value'],           'aq_y_value'),
        (['terrainClu',       'cl_terrainClu'],        'cl_terrain_cluster'),
        (['valley_are',       'cl_valley_are'],        'cl_valley_area'),
        (['hill_slope',       'cl_hill_slope'],        'cl_hill_slope'),
        (['plain_area',       'cl_plain_area'],        'cl_plain_area'),
        (['ridge_area',       'cl_ridge_area'],        'cl_ridge_area'),
        (['slopy_area',       'cl_slopy_area'],        'cl_slopy_area'),
        (['soge_block',       'sg_soge_block'],        'sg_block'),
        (['soge_district',    'sg_soge_district'],     'sg_district'),
        (['soge_objectid',    'sg_soge_objectid'],     'sg_objectid'),
        (['soge_tehsil',      'sg_soge_tehsil'],       'sg_tehsil'),
        (['pct_area_soge',    'sg_pct_area_soge'],     'sg_pct_area'),
        (['sgw_dev_pe',       'sg_sgw_dev_pe'],        'sg_sgw_dev_pct'),
        (['agwd_dom_i',       'sg_agwd_dom_i'],        'sg_agwd_dom_i'),
        (['agwd_irr',         'sg_agwd_irr'],          'sg_agwd_irr'),
        (['agwd_tot',         'sg_agwd_tot'],          'sg_agwd_tot'),
        (['ar_gwr_tot',       'sg_ar_gwr_tot'],        'sg_ar_gwr_tot'),
        (['class',            'sg_class'],             'sg_class'),
        (['code',             'sg_code'],              'sg_code'),
        (['max_intersection_area_ha', 'sg_max_intersection_area_ha'], 'sg_max_intersection_area_ha'),
        (['na_gwa',           'sg_na_gwa'],            'sg_na_gwa'),
        (['nat_discha',       'sg_nat_discha'],        'sg_nat_discha'),
        (['sgw_dev_pe',       'sg_sgw_dev_pe'],        'sg_sgw_dev_pct'),
        (['sum',              'ci_sum'],               'ci_sum'),
        (['total_cropable_area_ever_hydroyear_2017_2024',
          'ci_total_cropable_area_ever_hydroyear_2017_2024'], 'ci_croppable_area_hy_2017_2024'),
    ]

    actual_renames = []
    for candidates, final_name in rename_candidates:
        for src in candidates:
            if src in all_columns and src != final_name:
                actual_renames.append((src, final_name))
                break  # use first match, don't double-rename

    # deduplicate (same src appearing twice due to overlapping candidates)
    seen_src = set()
    actual_renames = [(s,d) for s,d in actual_renames if s not in seen_src and not seen_src.add(s)]

    if actual_renames:
        rclauses = ', '.join(['"' + s + '" AS "' + d + '"' for s,d in actual_renames])
        excl_sql = ', '.join(['"' + s + '"' for s,_ in actual_renames])
        con.execute("CREATE OR REPLACE TABLE joined_data AS SELECT * EXCLUDE (" + excl_sql + "), " + rclauses + " FROM joined_data")
        print(f"  Renamed {len(actual_renames)} columns")

    all_columns = get_columns()
    print(f"  Final column count after schema step: {len(all_columns)}")

    # ------------------------------------------------------------------ #
    # Step 7: Export to GeoParquet                                        #
    # ------------------------------------------------------------------ #
    print(f"\nStep 7/7: Exporting to {output_file}...")

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