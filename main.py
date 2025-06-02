# ===================== SEC 7: MAIN AREA - STATEMENT IMPORT & PROCESSING =======================
with st.expander("📂  Ultimate Chart Dashboard Import & Processing", expanded=True):
    st.markdown("### 📊 จัดการ Statement และข้อมูลดิบ")

    # --- ฟังก์ชันสำหรับแยกข้อมูลจากเนื้อหาไฟล์ Statement (CSV) ---
    # [!!! ใช้ฟังก์ชัน extract_data_from_report_content ที่แก้ไขล่าสุดจาก #75 ของคุณตรงนี้นะครับ !!!]
    # (ฟังก์ชันนี้ควรจะกรองแถว "balance" และแถวที่ไม่สมบูรณ์สำหรับ Deals ออกไปแล้ว)
    def extract_data_from_report_content(file_content_str_input):
        extracted_data = {}
        # ... (โค้ดทั้งหมดของฟังก์ชัน extract_data_from_report_content จาก #75) ...
        # ตรวจสอบให้แน่ใจว่า return extracted_data ที่มี keys:
        # 'deals', 'orders', 'positions', 'balance_summary', 'results_summary'
        # และ DataFrame 'deals' ได้ผ่านการกรองแถวที่ไม่ต้องการออกไปแล้ว
        
        # --- START: ส่วนที่คัดลอกมาจากโค้ดของคุณใน #35 (แต่มีการแก้ไขการกรอง Deals ใน #75) ---
        def safe_float_convert(value_str):
            if isinstance(value_str, (int, float)): return value_str
            try:
                clean_value = str(value_str).replace(" ", "").replace(",", "").replace("%", "")
                if clean_value.count('.') > 1:
                    parts = clean_value.split('.'); integer_part = "".join(parts[:-1]); decimal_part = parts[-1]
                    clean_value = integer_part + "." + decimal_part
                return float(clean_value)
            except (ValueError, Exception): return None

        lines = []
        if isinstance(file_content_str_input, str): lines = file_content_str_input.strip().split('\n')
        elif isinstance(file_content_str_input, bytes): lines = file_content_str_input.decode('utf-8', errors='replace').strip().split('\n')
        else:
            st.error("Error: Invalid file_content type for processing in extract_data_from_report_content.")
            return extracted_data 
        
        if not lines: 
            st.warning("Warning: File content is empty after splitting lines in extract_data_from_report_content.")
            return extracted_data

        section_raw_headers = {
            "Positions": "Time,Position,Symbol,Type,Volume,Price,S / L,T / P,Time,Price,Commission,Swap,Profit",
            "Orders": "Open Time,Order,Symbol,Type,Volume,Price,S / L,T / P,Time,State,,Comment",
            "Deals": "Time,Deal,Symbol,Type,Direction,Volume,Price,Order,Commission,Fee,Swap,Profit,Balance,Comment",
        }
        expected_cleaned_columns = {
            "Positions": ["Time", "Position", "Symbol", "Type", "Volume", "Price", "S_L", "T_P", "Close_Time_Pos", "Close_Price_Pos", "Commission_Pos", "Swap_Pos", "Profit_Pos"],
            "Orders": ["Open_Time_Ord", "Order_ID_Ord", "Symbol_Ord", "Type_Ord", "Volume_Ord", "Price_Ord", "S_L_Ord", "T_P_Ord", "Close_Time_Ord", "State_Ord", "Comment_Ord"],
            "Deals": ["Time_Deal", "Deal_ID", "Symbol_Deal", "Type_Deal", "Direction_Deal", "Volume_Deal", "Price_Deal", "Order_ID_Deal", "Commission_Deal", "Fee_Deal", "Swap_Deal", "Profit_Deal", "Balance_Deal", "Comment_Deal"],
        }
        section_order_for_tables = ["Positions", "Orders", "Deals"]
        section_header_indices = {}
        
        for line_idx, current_line_str in enumerate(lines):
            stripped_line = current_line_str.strip()
            for section_name, raw_header_template in section_raw_headers.items():
                if section_name not in section_header_indices:
                    first_col_of_template = raw_header_template.split(',')[0].strip()
                    if stripped_line.startswith(first_col_of_template) and raw_header_template in stripped_line:
                        section_header_indices[section_name] = line_idx; break
        
        for table_idx, section_name in enumerate(section_order_for_tables):
            section_key_lower = section_name.lower()
            extracted_data[section_key_lower] = pd.DataFrame()
            if section_name in section_header_indices:
                header_line_num = section_header_indices[section_name]
                data_start_line_num = header_line_num + 1
                data_end_line_num = len(lines)
                for next_table_name_idx in range(table_idx + 1, len(section_order_for_tables)):
                    next_table_section_name = section_order_for_tables[next_table_name_idx]
                    if next_table_section_name in section_header_indices:
                        data_end_line_num = section_header_indices[next_table_section_name]; break
                
                current_table_data_lines = [] # Renamed from current_table_data_lines_after_string_filter

                if st.session_state.get("debug_statement_processing_v2", False) and section_name == "Deals":
                    st.write(f"--- DEBUG [extract_data]: Raw lines being considered for SECTION: {section_name} ---")
                
                for line_num_for_data in range(data_start_line_num, data_end_line_num):
                    line_content_for_data = lines[line_num_for_data].strip()
                    
                    if not line_content_for_data:
                        if any(current_table_data_lines): break
                        else: continue
                    if line_content_for_data.startswith(("Balance:", "Credit Facility:", "Floating P/L:", "Equity:", "Results", "Total Net Profit:")): break
                    
                    is_another_header_line = False
                    for other_sec_name, other_raw_hdr in section_raw_headers.items():
                        if other_sec_name != section_name and line_content_for_data.startswith(other_raw_hdr.split(',')[0]) and other_raw_hdr in line_content_for_data:
                            is_another_header_line = True; break
                    if is_another_header_line: break
                    
                    # ***** START ACTUAL STRING-LEVEL FILTERING FOR "Deals" SECTION (from #75) *****
                    if section_name == "Deals":
                        cols_in_line = [col.strip() for col in line_content_for_data.split(',')]
                        
                        is_balance_type_row = False
                        if len(cols_in_line) > 3 and "balance" in cols_in_line[3].lower(): # Check Type_Deal (index 3)
                            is_balance_type_row = True
                        
                        missing_essential_identifiers = False
                        if len(cols_in_line) < 3: 
                            missing_essential_identifiers = True
                        elif not cols_in_line[0] or not cols_in_line[1] or not cols_in_line[2]: # Time_Deal, Deal_ID, or Symbol_Deal is empty
                            missing_essential_identifiers = True

                        if is_balance_type_row or missing_essential_identifiers:
                            if st.session_state.get("debug_statement_processing_v2", False):
                                st.write(f"DEBUG [extract_data]: SKIPPING Deals line: '{line_content_for_data}' (Balance Type: {is_balance_type_row}, Missing Identifiers: {missing_essential_identifiers})")
                            continue 
                    # ***** END ACTUAL STRING-LEVEL FILTERING FOR "Deals" SECTION *****
                        
                    current_table_data_lines.append(line_content_for_data)

                if st.session_state.get("debug_statement_processing_v2", False) and section_name == "Deals":
                    st.write(f"--- DEBUG [extract_data]: Lines for Deals AFTER string filtering (to be parsed by pd.read_csv): {len(current_table_data_lines)} ---")
                    if current_table_data_lines: st.text("\n".join(current_table_data_lines[:20]))

                if current_table_data_lines:
                    csv_data_str = "\n".join(current_table_data_lines)
                    try:
                        df_section = pd.read_csv(io.StringIO(csv_data_str),
                                                 header=None, names=expected_cleaned_columns[section_name],
                                                 skipinitialspace=True, on_bad_lines='warn', engine='python', dtype=str)
                        df_section.dropna(how='all', inplace=True)
                        final_cols = expected_cleaned_columns[section_name]
                        for col in final_cols:
                            if col not in df_section.columns: df_section[col] = ""
                        df_section = df_section[final_cols]

                        # Secondary DataFrame-level filtering (can be removed if string filtering is sufficient)
                        if section_name == "Deals" and not df_section.empty:
                             if "Symbol_Deal" in df_section.columns: 
                                 df_section = df_section[df_section["Symbol_Deal"].astype(str).str.strip() != ""]
                             if st.session_state.get("debug_statement_processing_v2", False):
                                st.write(f"DEBUG: Deals DataFrame after pd.read_csv and potential secondary filtering ({len(df_section)} rows left):")
                                if not df_section.empty: st.dataframe(df_section.head())
                        
                        if not df_section.empty:
                            extracted_data[section_key_lower] = df_section
                    except Exception as e_parse_df:
                        if st.session_state.get("debug_statement_processing_v2", False):
                            st.error(f"Error parsing table data for {section_name}: {e_parse_df}")
                            st.text(f"Problematic CSV data for {section_name}:\n{csv_data_str[:500]}")
        
        balance_summary_dict = {}
        balance_start_line_idx = -1
        for i, line in enumerate(lines):
            if line.strip().startswith("Balance:"): balance_start_line_idx = i; break
        if balance_start_line_idx != -1:
            for i in range(balance_start_line_idx, min(balance_start_line_idx + 8, len(lines))):
                line_stripped = lines[i].strip();
                if not line_stripped : continue
                if line_stripped.startswith(("Results", "Total Net Profit:")) and i > balance_start_line_idx: break
                parts = [p.strip() for p in line_stripped.split(',') if p.strip()]; temp_key = ""; val_expected_next = False
                for part_idx, part_val in enumerate(parts):
                    if not part_val: continue
                    if ':' in part_val:
                        key_str, val_str = part_val.split(':', 1); key_clean = key_str.strip().replace(" ", "_").replace(".", "").replace("/","_").lower(); val_strip = val_str.strip()
                        if val_strip: balance_summary_dict[key_clean] = safe_float_convert(val_strip.split(' ')[0]); val_expected_next = False; temp_key = ""
                        else: temp_key = key_clean; val_expected_next = True
                    elif val_expected_next: balance_summary_dict[temp_key] = safe_float_convert(part_val.split(' ')[0]); temp_key = ""; val_expected_next = False
        essential_balance_keys = ["balance", "credit_facility", "floating_p_l", "equity", "free_margin", "margin", "margin_level"]
        for k_b in essential_balance_keys:
            if k_b not in balance_summary_dict: balance_summary_dict[k_b] = 0.0
        extracted_data['balance_summary'] = balance_summary_dict
        
        results_summary_dict = {}
        stat_definitions_map = {
            "Total Net Profit": "Total_Net_Profit", "Gross Profit": "Gross_Profit", "Gross Loss": "Gross_Loss", "Profit Factor": "Profit_Factor", "Expected Payoff": "Expected_Payoff",
            "Recovery Factor": "Recovery_Factor", "Sharpe Ratio": "Sharpe_Ratio", "Balance Drawdown Absolute": "Balance_Drawdown_Absolute", "Balance Drawdown Maximal": "Balance_Drawdown_Maximal",
            "Balance Drawdown Relative": "Balance_Drawdown_Relative_Percent", "Total Trades": "Total_Trades", "Short Trades (won %)": "Short_Trades", "Long Trades (won %)": "Long_Trades",
            "Profit Trades (% of total)": "Profit_Trades", "Loss Trades (% of total)": "Loss_Trades", "Largest profit trade": "Largest_profit_trade", "Largest loss trade": "Largest_loss_trade",
            "Average profit trade": "Average_profit_trade", "Average loss trade": "Average_loss_trade", "Maximum consecutive wins ($)": "Maximum_consecutive_wins_Count",
            "Maximal consecutive profit (count)": "Maximal_consecutive_profit_Amount", "Average consecutive wins": "Average_consecutive_wins",
            "Maximum consecutive losses ($)": "Maximum_consecutive_losses_Count", "Maximal consecutive loss (count)": "Maximal_consecutive_loss_Amount", "Average consecutive losses": "Average_consecutive_losses"
        }
        results_start_line_idx = -1; results_section_processed_lines = 0; max_lines_for_results = 30
        for i_res, line_res in enumerate(lines):
            if results_start_line_idx == -1 and (line_res.strip().startswith("Results") or line_res.strip().startswith("Total Net Profit:")): results_start_line_idx = i_res; continue
            if results_start_line_idx != -1 and results_section_processed_lines < max_lines_for_results:
                line_stripped_res = line_res.strip()
                if not line_stripped_res:
                    if results_section_processed_lines > 2: break
                    else: continue
                results_section_processed_lines += 1; row_cells = [cell.strip() for cell in line_stripped_res.split(',')]
                for c_idx, cell_content in enumerate(row_cells):
                    if not cell_content: continue
                    current_label = cell_content.replace(':', '').strip()
                    if current_label in stat_definitions_map:
                        gsheet_key = stat_definitions_map[current_label]
                        for k_val_search in range(1, 5):
                            if (c_idx + k_val_search) < len(row_cells):
                                raw_value_from_cell = row_cells[c_idx + k_val_search]
                                if raw_value_from_cell:
                                    value_part_before_paren = raw_value_from_cell.split('(')[0].strip(); numeric_value = safe_float_convert(value_part_before_paren)
                                    if numeric_value is not None:
                                        results_summary_dict[gsheet_key] = numeric_value
                                        if '(' in raw_value_from_cell and ')' in raw_value_from_cell:
                                            try:
                                                paren_content_str = raw_value_from_cell[raw_value_from_cell.find('(')+1:raw_value_from_cell.find(')')].strip().replace('%',''); paren_numeric_value = safe_float_convert(paren_content_str)
                                                if paren_numeric_value is not None:
                                                    if current_label == "Balance Drawdown Maximal": results_summary_dict["Balance_Drawdown_Maximal_Percent"] = paren_numeric_value
                                                    elif current_label == "Balance Drawdown Relative": results_summary_dict["Balance_Drawdown_Relative_Amount"] = paren_numeric_value
                                                    elif current_label == "Short Trades (won %)": results_summary_dict["Short_Trades_won_Percent"] = paren_numeric_value
                                                    elif current_label == "Long Trades (won %)": results_summary_dict["Long_Trades_won_Percent"] = paren_numeric_value
                                                    elif current_label == "Profit Trades (% of total)": results_summary_dict["Profit_Trades_Percent_of_total"] = paren_numeric_value
                                                    elif current_label == "Loss Trades (% of total)": results_summary_dict["Loss_Trades_Percent_of_total"] = paren_numeric_value
                                                    elif current_label == "Maximum consecutive wins ($)": results_summary_dict["Maximum_consecutive_wins_Profit"] = paren_numeric_value
                                                    elif current_label == "Maximal consecutive profit (count)": results_summary_dict["Maximal_consecutive_profit_Count"] = paren_numeric_value
                                                    elif current_label == "Maximum consecutive losses ($)": results_summary_dict["Maximum_consecutive_losses_Profit"] = paren_numeric_value
                                                    elif current_label == "Maximal consecutive loss (count)": results_summary_dict["Maximal_consecutive_loss_Count"] = paren_numeric_value
                                            except Exception: pass
                                        break
                if line_stripped_res.startswith("Average consecutive losses"): break
            elif results_start_line_idx != -1 and results_section_processed_lines >= max_lines_for_results: break
        extracted_data['balance_summary'] = balance_summary_dict
        extracted_data['results_summary'] = results_summary_dict
        return extracted_data
    # --- END: ฟังก์ชัน extract_data_from_report_content (ที่แก้ไขแล้ว) ---

    # --- START: ฟังก์ชันใหม่/แก้ไข สำหรับบันทึกข้อมูลพร้อม Deduplication และ Header Handling ---
    # (ฟังก์ชันนี้จะถูกเรียกโดย save_deals_to_actual_trades, save_orders_to_gsheets, save_positions_to_gsheets)
    def save_transactional_data_to_gsheets(ws, df_input, unique_id_col, expected_headers, data_type_name, portfolio_id, portfolio_name, source_file_name="N/A", import_batch_id="N/A"):
        if df_input is None or df_input.empty:
            return True, 0, 0 # No data to process, count as success with 0 new/skipped
        try:
            if ws is None: 
                st.error(f"({data_type_name}) Worksheet object is None. Cannot proceed.")
                return False, 0, 0

            current_headers = []
            header_check_successful = False
            if ws.row_count > 0:
                try:
                    current_headers = ws.row_values(1)
                    header_check_successful = True
                except gspread.exceptions.APIError as e_api_header:
                    if e_api_header.response.status_code == 429: # Quota error
                        st.warning(f"Quota exceeded while trying to get headers for '{ws.title}'. Will proceed assuming headers might need update.")
                        current_headers = [] # Assume headers need update if quota hit
                    else: raise # Re-raise other API errors
                except Exception as e_get_header:
                    st.warning(f"Could not get header for '{ws.title}': {e_get_header}. Will attempt to write/update headers.")
                    current_headers = []
            
            # Ensure headers are correct
            if not header_check_successful or not current_headers or all(h == "" for h in current_headers) or set(current_headers) != set(expected_headers):
                try:
                    ws.update([expected_headers], value_input_option='USER_ENTERED')
                    st.info(f"Headers written/updated for '{ws.title}'.")
                except Exception as e_update_header:
                    st.error(f"Failed to write/update headers for '{ws.title}': {e_update_header}")
                    return False, 0, 0

            existing_ids = set()
            if ws.row_count > 1: # Only fetch if there's data beyond a potential header
                try:
                    all_sheet_records = ws.get_all_records(
                        expected_headers=expected_headers,
                        numericise_ignore=['all'] 
                    )
                    if all_sheet_records:
                        df_existing_sheet_data = pd.DataFrame(all_sheet_records)
                        if unique_id_col in df_existing_sheet_data.columns and 'PortfolioID' in df_existing_sheet_data.columns:
                            df_existing_sheet_data['PortfolioID'] = df_existing_sheet_data['PortfolioID'].astype(str)
                            df_portfolio_data = df_existing_sheet_data[df_existing_sheet_data['PortfolioID'] == str(portfolio_id)]
                            if not df_portfolio_data.empty and unique_id_col in df_portfolio_data.columns:
                                existing_ids = set(df_portfolio_data[unique_id_col].astype(str).str.strip().tolist())
                except gspread.exceptions.APIError as e_api_get_all:
                    if e_api_get_all.response.status_code == 429: 
                        st.warning(f"Quota exceeded while trying to get existing records from '{ws.title}' for {data_type_name}. Deduplication might be incomplete for this run.")
                        existing_ids = set() 
                    else: 
                        st.warning(f"API error (not Quota) getting existing records from '{ws.title}' for {data_type_name} ({e_api_get_all}). Proceeding with empty existing_ids.")
                        existing_ids = set()
                except Exception as e_get_records:
                    st.warning(f"Could not reliably get existing records from '{ws.title}' for {data_type_name} ({e_get_records}). Proceeding assuming no initial duplicates for this run.")
                    existing_ids = set()
            else: 
                 if st.session_state.get("debug_statement_processing_v2", False) :
                    st.write(f"DEBUG ({ws.title}): Sheet has only header or is empty. Skipping get_all_records for {data_type_name}.")


            df_to_check = df_input.copy()
            # Ensure unique_id_col exists before trying to use it for deduplication
            if unique_id_col not in df_to_check.columns:
                st.error(f"Unique ID column '{unique_id_col}' is MISSING from the data extracted for '{data_type_name}'. All data will be treated as new.")
                new_df = df_to_check # Treat all as new if ID column is missing
            else:
                df_to_check[unique_id_col] = df_to_check[unique_id_col].astype(str).str.strip()
                new_df = df_to_check[~df_to_check[unique_id_col].isin(existing_ids)]

            num_new = len(new_df)
            num_duplicates_skipped = len(df_to_check) - num_new

            if st.session_state.get("debug_statement_processing_v2", False) and data_type_name == "Deals":
                if unique_id_col in df_to_check.columns:
                     st.write(f"DEBUG ({ws.title}): Unique IDs from new Deals data (df_to_check['{unique_id_col}']):")
                     st.dataframe(df_to_check[[unique_id_col]].head(10))
                else:
                     st.write(f"DEBUG ({ws.title}): Unique ID column '{unique_id_col}' not found in df_to_check for Deals.")
                st.write(f"DEBUG ({ws.title}): Existing IDs in GSheet for this Portfolio ({len(existing_ids)} items):")
                st.json(list(existing_ids)[:10] if existing_ids else "No existing IDs found or readable from GSheet")
                st.write(f"DEBUG ({ws.title}): Found {num_new} 'new' deal(s) to be added (content shown below if any):")
                if not new_df.empty: st.dataframe(new_df)
                else: st.write("No new deals found after deduplication.")

            if new_df.empty:
                return True, num_new, num_duplicates_skipped

            df_to_save = pd.DataFrame(columns=expected_headers)
            for col in expected_headers:
                if col in new_df.columns:
                    df_to_save[col] = new_df[col]
            
            df_to_save["PortfolioID"] = str(portfolio_id)
            df_to_save["PortfolioName"] = str(portfolio_name)
            df_to_save["SourceFile"] = str(source_file_name)
            df_to_save["ImportBatchID"] = str(import_batch_id)
            
            for col in expected_headers:
                if col not in df_to_save.columns:
                    df_to_save[col] = ""
            df_to_save = df_to_save[expected_headers]

            list_of_lists = df_to_save.astype(str).replace('nan', '').replace('None','').fillna("").values.tolist()

            if list_of_lists:
                ws.append_rows(list_of_lists, value_input_option='USER_ENTERED')
            return True, num_new, num_duplicates_skipped

        except gspread.exceptions.APIError as e_api:
            st.error(f"❌ ({ws.title}) Google Sheets API Error ({data_type_name}): {e_api}")
            return False, 0, 0
        except Exception as e:
            st.error(f"❌ ({ws.title}) เกิดข้อผิดพลาดในการบันทึก {data_type_name}: {e}")
            st.exception(e)
            return False, 0, 0

    # --- ฟังก์ชัน save_deals_to_actual_trades, save_orders_to_gsheets, save_positions_to_gsheets ---
    # (ปรับให้รับ ws และส่ง import_batch_id)
    def save_deals_to_actual_trades(ws, df_deals_input, portfolio_id, portfolio_name, source_file_name="N/A", import_batch_id="N/A"):
        expected_headers_deals = ["Time_Deal", "Deal_ID", "Symbol_Deal", "Type_Deal", "Direction_Deal", "Volume_Deal", "Price_Deal", "Order_ID_Deal", "Commission_Deal", "Fee_Deal", "Swap_Deal", "Profit_Deal", "Balance_Deal", "Comment_Deal", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"]
        return save_transactional_data_to_gsheets(ws, df_deals_input, "Deal_ID", expected_headers_deals, "Deals", portfolio_id, portfolio_name, source_file_name, import_batch_id)

    def save_orders_to_gsheets(ws, df_orders_input, portfolio_id, portfolio_name, source_file_name="N/A", import_batch_id="N/A"):
        expected_headers_orders = ["Open_Time_Ord", "Order_ID_Ord", "Symbol_Ord", "Type_Ord", "Volume_Ord", "Price_Ord", "S_L_Ord", "T_P_Ord", "Close_Time_Ord", "State_Ord", "Comment_Ord", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"]
        return save_transactional_data_to_gsheets(ws, df_orders_input, "Order_ID_Ord", expected_headers_orders, "Orders", portfolio_id, portfolio_name, source_file_name, import_batch_id)

    def save_positions_to_gsheets(ws, df_positions_input, portfolio_id, portfolio_name, source_file_name="N/A", import_batch_id="N/A"):
        expected_headers_positions = ["Time", "Position", "Symbol", "Type", "Volume", "Price", "S_L", "T_P", "Close_Time_Pos", "Close_Price_Pos", "Commission_Pos", "Swap_Pos", "Profit_Pos", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"]
        return save_transactional_data_to_gsheets(ws, df_positions_input, "Position", expected_headers_positions, "Positions", portfolio_id, portfolio_name, source_file_name, import_batch_id)
    
    # --- ฟังก์ชัน save_results_summary_to_gsheets (ปรับให้รับ ws และมีการตรวจสอบเนื้อหาซ้ำ) ---
    def save_results_summary_to_gsheets(ws, balance_summary_data, results_summary_data, portfolio_id, portfolio_name, source_file_name="N/A", import_batch_id="N/A"):
        try:
            if ws is None:
                st.error(f"({WORKSHEET_STATEMENT_SUMMARIES}) Worksheet object is None. Cannot save summary.")
                return False 
            
            expected_headers = ["Timestamp", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID", "Balance", "Equity", "Free_Margin", "Margin", "Floating_P_L", "Margin_Level", "Total_Net_Profit", "Gross_Profit", "Gross_Loss", "Profit_Factor", "Expected_Payoff", "Recovery_Factor", "Sharpe_Ratio", "Balance_Drawdown_Absolute", "Balance_Drawdown_Maximal", "Balance_Drawdown_Maximal_Percent", "Balance_Drawdown_Relative_Percent", "Balance_Drawdown_Relative_Amount", "Total_Trades", "Short_Trades", "Short_Trades_won_Percent", "Long_Trades", "Long_Trades_won_Percent", "Profit_Trades", "Profit_Trades_Percent_of_total", "Loss_Trades", "Loss_Trades_Percent_of_total", "Largest_profit_trade", "Largest_loss_trade", "Average_profit_trade", "Average_loss_trade", "Maximum_consecutive_wins_Count", "Maximum_consecutive_wins_Profit", "Maximum_consecutive_losses_Count", "Maximum_consecutive_losses_Profit", "Maximal_consecutive_profit_Amount", "Maximal_consecutive_profit_Count", "Maximal_consecutive_loss_Amount", "Maximal_consecutive_loss_Count", "Average_consecutive_wins", "Average_consecutive_losses"]
            
            current_headers_ws = []
            if ws.row_count > 0:
                try: current_headers_ws = ws.row_values(1)
                except Exception: pass
            if not current_headers_ws or all(h == "" for h in current_headers_ws) or set(current_headers_ws) != set(expected_headers):
                ws.update([expected_headers], value_input_option='USER_ENTERED')
            
            new_summary_row_data = {
                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "PortfolioID": str(portfolio_id), 
                "PortfolioName": str(portfolio_name), "SourceFile": str(source_file_name), 
                "ImportBatchID": str(import_batch_id) 
            }
            balance_key_map = {"balance":"Balance", "equity":"Equity", "free_margin":"Free_Margin", "margin":"Margin", "floating_p_l":"Floating_P_L", "margin_level":"Margin_Level"}
            if isinstance(balance_summary_data, dict): 
                for k, v in balance_summary_data.items():
                    if k in balance_key_map: new_summary_row_data[balance_key_map[k]] = v
            if isinstance(results_summary_data, dict): 
                for k,v in results_summary_data.items():
                    if k in expected_headers: new_summary_row_data[k] = v
            
            comparison_keys = [
                "Balance", "Equity", "Total_Net_Profit", "Gross_Profit", "Gross_Loss", "Profit_Factor", 
                "Expected_Payoff", "Balance_Drawdown_Absolute", "Balance_Drawdown_Maximal", 
                "Balance_Drawdown_Maximal_Percent", "Balance_Drawdown_Relative_Percent", "Total_Trades", 
                "Short_Trades", "Short_Trades_won_Percent", "Long_Trades", "Long_Trades_won_Percent", 
                "Profit_Trades", "Profit_Trades_Percent_of_total", "Loss_Trades", "Loss_Trades_Percent_of_total", 
                "Largest_profit_trade", "Largest_loss_trade", "Average_profit_trade", "Average_loss_trade", 
                "Maximum_consecutive_wins_Count", "Maximum_consecutive_wins_Profit", 
                "Maximum_consecutive_losses_Count", "Maximum_consecutive_losses_Profit",
                "Maximal_consecutive_profit_Amount", "Maximal_consecutive_profit_Count",
                "Maximal_consecutive_loss_Amount", "Maximal_consecutive_loss_Count",
                "Average_consecutive_wins", "Average_consecutive_losses"
            ]
            new_summary_comparable_values = []
            for k in comparison_keys:
                val = new_summary_row_data.get(k)
                if isinstance(val, float): new_summary_comparable_values.append(f"{val:.2f}") 
                else: new_summary_comparable_values.append(str(val if pd.notna(val) else "").strip())
            new_summary_fingerprint = tuple(new_summary_comparable_values)

            if ws.row_count > 1: 
                try:
                    existing_summaries_records = ws.get_all_records(expected_headers=expected_headers, numericise_ignore=['all'])
                    df_existing_summaries = pd.DataFrame(existing_summaries_records)
                    if not df_existing_summaries.empty and 'PortfolioID' in df_existing_summaries.columns:
                        df_portfolio_summaries = df_existing_summaries[df_existing_summaries['PortfolioID'].astype(str) == str(portfolio_id)]
                        for index, existing_row in df_portfolio_summaries.iterrows():
                            existing_summary_comparable_values = []
                            for k in comparison_keys:
                                val = existing_row.get(k)
                                try: existing_summary_comparable_values.append(f"{float(val):.2f}")
                                except (ValueError, TypeError): existing_summary_comparable_values.append(str(val if pd.notna(val) else "").strip())
                            existing_summary_fingerprint = tuple(existing_summary_comparable_values)
                            if existing_summary_fingerprint == new_summary_fingerprint:
                                st.info(f"({ws.title}) ข้อมูล Summary ที่มีเนื้อหาเหมือนกันสำหรับพอร์ต '{portfolio_name}' นี้มีอยู่แล้ว จะไม่บันทึกซ้ำ (ImportBatchID ปัจจุบัน: {import_batch_id})")
                                return True # Indicate operation was 'successful' in the sense that it behaved as expected (skipped duplicate)
                except gspread.exceptions.APIError as e_api_get_sum: # Catch API error during get_all_records
                    if e_api_get_sum.response.status_code == 429: # Quota error
                        st.warning(f"Quota exceeded while trying to get existing summaries from '{ws.title}' for content check. Proceeding with append for this run.")
                    else:
                        st.warning(f"API error getting existing summaries from '{ws.title}' for content check ({e_api_get_sum}). Proceeding with append.")
                except Exception as e_get_sum_records:
                    st.warning(f"Could not reliably get existing summaries from '{ws.title}' for content check ({e_get_sum_records}). Proceeding with append.")

            final_row_values = [str(new_summary_row_data.get(h, "")).strip() for h in expected_headers]
            ws.append_rows([final_row_values], value_input_option='USER_ENTERED')
            return True 
        except gspread.exceptions.APIError as e_api: 
            st.error(f"❌ ({ws.title}) Google Sheets API Error (Summary): {e_api}")
            return False
        except Exception as e: 
            st.error(f"❌ ({ws.title}) เกิดข้อผิดพลาดในการบันทึก Statement Summaries: {e}")
            st.exception(e)
            return False
    # --- END: ฟังก์ชัน save_... ---

    st.markdown("---")
    st.subheader("📤 อัปโหลด Statement Report (CSV) เพื่อประมวลผลและบันทึก")
    
    uploaded_file_statement = st.file_uploader( 
        "ลากและวางไฟล์ Statement Report (CSV) ที่นี่ หรือคลิกเพื่อเลือกไฟล์",
        type=["csv"],
        key="ultimate_stmt_uploader_v7_final" # New key
    )

    st.checkbox("⚙️ เปิดโหมด Debug (แสดงข้อมูลที่แยกได้)", value=False, key="debug_statement_processing_v2")
    
    active_portfolio_id_for_actual = st.session_state.get('active_portfolio_id_gs', None)
    active_portfolio_name_for_actual = st.session_state.get('active_portfolio_name_gs', None)

    if uploaded_file_statement:
        file_name_for_saving = uploaded_file_statement.name
        file_size_for_saving = uploaded_file_statement.size 
        
        import hashlib 
        file_hash_for_saving = ""
        try:
            uploaded_file_statement.seek(0) 
            file_content_for_hash = uploaded_file_statement.read()
            uploaded_file_statement.seek(0) 
            file_hash_for_saving = hashlib.md5(file_content_for_hash).hexdigest()
        except Exception as e_hash:
            file_hash_for_saving = f"hash_error_{random.randint(1000,9999)}"
            st.warning(f"ไม่สามารถคำนวณ File Hash: {e_hash}")

        if not active_portfolio_id_for_actual: 
            st.error("กรุณาเลือกพอร์ตที่ใช้งาน (Active Portfolio) ใน Sidebar ก่อนประมวลผล Statement.")
            st.stop()
        
        st.info(f"ไฟล์ที่อัปโหลด: {file_name_for_saving} (ขนาด: {file_size_for_saving} bytes, Hash: {file_hash_for_saving})")
        gc_for_sheets = get_gspread_client()
        if not gc_for_sheets: 
            st.error("ไม่สามารถเชื่อมต่อ Google Sheets Client ได้")
            st.stop()

        # --- START: โค้ดสำหรับเปิด/สร้าง Worksheet อัตโนมัติ และจัดการ Header ---
        ws_dict = {}
        default_sheet_specs = {"rows": "100", "cols": "26"} 
        if 'WORKSHEET_UPLOAD_HISTORY' not in globals(): WORKSHEET_UPLOAD_HISTORY = "UploadHistory" # Ensure defined

        worksheet_definitions = {
            WORKSHEET_UPLOAD_HISTORY: {"rows": "1000", "cols": "10", "headers": ["UploadTimestamp", "PortfolioID", "PortfolioName", "FileName", "FileSize", "FileHash", "Status", "ImportBatchID", "Notes"]},
            WORKSHEET_ACTUAL_TRADES: {"rows": "1000", "cols": "20", "headers": ["Time_Deal", "Deal_ID", "Symbol_Deal", "Type_Deal", "Direction_Deal", "Volume_Deal", "Price_Deal", "Order_ID_Deal", "Commission_Deal", "Fee_Deal", "Swap_Deal", "Profit_Deal", "Balance_Deal", "Comment_Deal", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"]},
            WORKSHEET_ACTUAL_ORDERS: {"rows": "1000", "cols": "15", "headers": ["Open_Time_Ord", "Order_ID_Ord", "Symbol_Ord", "Type_Ord", "Volume_Ord", "Price_Ord", "S_L_Ord", "T_P_Ord", "Close_Time_Ord", "State_Ord", "Comment_Ord", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"]},
            WORKSHEET_ACTUAL_POSITIONS: {"rows": "1000", "cols": "20", "headers": ["Time", "Position", "Symbol", "Type", "Volume", "Price", "S_L", "T_P", "Close_Time_Pos", "Close_Price_Pos", "Commission_Pos", "Swap_Pos", "Profit_Pos", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"]},
            WORKSHEET_STATEMENT_SUMMARIES: {"rows": "1000", "cols": "40", "headers": ["Timestamp", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID", "Balance", "Equity", "Free_Margin", "Margin", "Floating_P_L", "Margin_Level", "Total_Net_Profit", "Gross_Profit", "Gross_Loss", "Profit_Factor", "Expected_Payoff", "Recovery_Factor", "Sharpe_Ratio", "Balance_Drawdown_Absolute", "Balance_Drawdown_Maximal", "Balance_Drawdown_Maximal_Percent", "Balance_Drawdown_Relative_Percent", "Balance_Drawdown_Relative_Amount", "Total_Trades", "Short_Trades", "Short_Trades_won_Percent", "Long_Trades", "Long_Trades_won_Percent", "Profit_Trades", "Profit_Trades_Percent_of_total", "Loss_Trades", "Loss_Trades_Percent_of_total", "Largest_profit_trade", "Largest_loss_trade", "Average_profit_trade", "Average_loss_trade", "Maximum_consecutive_wins_Count", "Maximum_consecutive_wins_Profit", "Maximum_consecutive_losses_Count", "Maximum_consecutive_losses_Profit", "Maximal_consecutive_profit_Amount", "Maximal_consecutive_profit_Count", "Maximal_consecutive_loss_Amount", "Maximal_consecutive_loss_Count", "Average_consecutive_wins", "Average_consecutive_losses"]}
        }

        all_sheets_successfully_accessed_or_created = True 
        sh_trade_log = None 
        try:
            sh_trade_log = gc_for_sheets.open(GOOGLE_SHEET_NAME)
            for ws_name, specs in worksheet_definitions.items():
                try:
                    ws_dict[ws_name] = sh_trade_log.worksheet(ws_name)
                    current_ws_headers_check = []
                    if ws_dict[ws_name].row_count > 0 :
                        try: current_ws_headers_check = ws_dict[ws_name].row_values(1)
                        except Exception: pass 
                    if not current_ws_headers_check or all(h=="" for h in current_ws_headers_check) or set(current_ws_headers_check) != set(specs["headers"]):
                        if "headers" in specs: 
                            ws_dict[ws_name].update([specs["headers"]], value_input_option='USER_ENTERED')
                            st.info(f"Ensured/Updated headers for '{ws_name}' sheet.")
                except gspread.exceptions.WorksheetNotFound:
                    st.info(f"Worksheet '{ws_name}' not found. Creating it now...")
                    try:
                        new_ws = sh_trade_log.add_worksheet(title=ws_name, rows=specs.get("rows", default_sheet_specs["rows"]), cols=specs.get("cols", default_sheet_specs["cols"]))
                        ws_dict[ws_name] = new_ws 
                        if "headers" in specs: 
                            new_ws.update([specs["headers"]], value_input_option='USER_ENTERED') 
                            st.info(f"Created worksheet '{ws_name}' and added headers.")
                    except Exception as e_add_ws:
                        st.error(f"❌ Failed to create worksheet '{ws_name}': {e_add_ws}")
                        all_sheets_successfully_accessed_or_created = False; break 
                except Exception as e_open_ws: 
                    st.error(f"❌ Error accessing worksheet '{ws_name}': {e_open_ws}")
                    all_sheets_successfully_accessed_or_created = False; break
            
            if not all_sheets_successfully_accessed_or_created:
                st.error("One or more essential worksheets could not be accessed or created. Aborting.")
                st.stop()
        
        except gspread.exceptions.APIError as e_api:
            st.error(f"❌ Google Sheets API Error (Opening Spreadsheet or Initial Worksheet Access/Creation): {e_api}.")
            st.stop()
        except Exception as e_setup: 
            st.error(f"❌ เกิดข้อผิดพลาดในการเข้าถึง Spreadsheet หรือสร้าง Worksheet: {type(e_setup).__name__} - {str(e_setup)[:200]}...")
            st.stop()

        for ws_name_key in worksheet_definitions.keys():
            if ws_name_key not in ws_dict or ws_dict[ws_name_key] is None:
                st.error(f"❌ ไม่สามารถเข้าถึงหรือสร้าง Worksheet '{ws_name_key}' ได้อย่างสมบูรณ์ โปรดตรวจสอบ Google Sheets และลองอีกครั้ง")
                st.stop()  
        # ***** END: โค้ดสำหรับเปิด/สร้าง Worksheet อัตโนมัติ *****

        import_batch_id = str(uuid.uuid4()) 
        current_upload_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        is_duplicate_file_found = False # This is the file-level check
        try:
            history_records = ws_dict[WORKSHEET_UPLOAD_HISTORY].get_all_records(numericise_ignore=['all'])
            for record in history_records:
                try: record_file_size_val = int(float(str(record.get("FileSize","0")).replace(",","")))
                except: record_file_size_val = 0
                if str(record.get("PortfolioID","")) == str(active_portfolio_id_for_actual) and \
                   record.get("FileName","") == file_name_for_saving and \
                   record_file_size_val == file_size_for_saving and \
                   (not file_hash_for_saving or record.get("FileHash","") == file_hash_for_saving or file_hash_for_saving.startswith("hash_")) and \
                   str(record.get("Status","")).startswith("Success"):
                    is_duplicate_file_found = True; break # Found a previous successful upload of the same file
        except Exception as e_hist_read:
            st.warning(f"Could not read UploadHistory for duplicate file check: {e_hist_read}")

        try:
            ws_dict[WORKSHEET_UPLOAD_HISTORY].append_row([
                current_upload_timestamp, str(active_portfolio_id_for_actual), str(active_portfolio_name_for_actual),
                file_name_for_saving, file_size_for_saving, file_hash_for_saving,
                "Processing", import_batch_id, "Attempting to process file."
            ])
        except Exception as e_log_init:
            st.error(f"ไม่สามารถบันทึก Log เริ่มต้นใน {WORKSHEET_UPLOAD_HISTORY}: {e_log_init}")
            st.stop() 

        st.markdown(f"--- \n**Import Batch ID: `{import_batch_id}`**")
        st.info(f"กำลังประมวลผลไฟล์: {file_name_for_saving}")
        
        overall_processing_successful = True
        any_new_transactional_data_added = False 
        save_results_details = {} 
        
        try:
            uploaded_file_statement.seek(0) 
            file_content_str = uploaded_file_statement.getvalue().decode("utf-8", errors="replace")
            
            with st.spinner(f"กำลังแยกส่วนข้อมูลจาก {file_name_for_saving}..."): 
                extracted_sections = extract_data_from_report_content(file_content_str)
            
            if st.session_state.get("debug_statement_processing_v2", False): 
                # ... (โค้ด Debug extracted_sections) ...
                pass

            if not extracted_sections: 
                overall_processing_successful = False
                save_results_details['Extraction'] = {'ok': False, 'notes': "Failed to extract sections from file."}
            else:
                st.subheader("💾 กำลังบันทึกข้อมูลส่วนต่างๆไปยัง Google Sheets...")
                
                deals_df = extracted_sections.get('deals', pd.DataFrame())
                ok, new_count, skipped_count = save_deals_to_actual_trades(ws_dict[WORKSHEET_ACTUAL_TRADES], deals_df, active_portfolio_id_for_actual, active_portfolio_name_for_actual, file_name_for_saving, import_batch_id)
                save_results_details['Deals'] = {'ok': ok, 'new': new_count, 'skipped': skipped_count, 'notes': f"Deals: New={new_count}, Skipped={skipped_count}, Success={ok}"}
                if ok: st.write(f"✔️ ({WORKSHEET_ACTUAL_TRADES}) Deals: เพิ่ม {new_count}, ข้าม {skipped_count}.")
                else: st.error(f"❌ ({WORKSHEET_ACTUAL_TRADES}) Deals: การบันทึกล้มเหลว")
                if new_count > 0: any_new_transactional_data_added = True
                if not ok: overall_processing_successful = False
                
                orders_df = extracted_sections.get('orders', pd.DataFrame())
                ok, new_count, skipped_count = save_orders_to_gsheets(ws_dict[WORKSHEET_ACTUAL_ORDERS], orders_df, active_portfolio_id_for_actual, active_portfolio_name_for_actual, file_name_for_saving, import_batch_id)
                save_results_details['Orders'] = {'ok': ok, 'new': new_count, 'skipped': skipped_count, 'notes': f"Orders: New={new_count}, Skipped={skipped_count}, Success={ok}"}
                if ok: st.write(f"✔️ ({WORKSHEET_ACTUAL_ORDERS}) Orders: เพิ่ม {new_count}, ข้าม {skipped_count}.")
                else: st.error(f"❌ ({WORKSHEET_ACTUAL_ORDERS}) Orders: การบันทึกล้มเหลว")
                if new_count > 0: any_new_transactional_data_added = True
                if not ok: overall_processing_successful = False

                positions_df = extracted_sections.get('positions', pd.DataFrame())
                ok, new_count, skipped_count = save_positions_to_gsheets(ws_dict[WORKSHEET_ACTUAL_POSITIONS], positions_df, active_portfolio_id_for_actual, active_portfolio_name_for_actual, file_name_for_saving, import_batch_id)
                save_results_details['Positions'] = {'ok': ok, 'new': new_count, 'skipped': skipped_count, 'notes': f"Positions: New={new_count}, Skipped={skipped_count}, Success={ok}"}
                if ok: st.write(f"✔️ ({WORKSHEET_ACTUAL_POSITIONS}) Positions: เพิ่ม {new_count}, ข้าม {skipped_count}.")
                else: st.error(f"❌ ({WORKSHEET_ACTUAL_POSITIONS}) Positions: การบันทึกล้มเหลว")
                if new_count > 0: any_new_transactional_data_added = True
                if not ok: overall_processing_successful = False
                
                balance_summary = extracted_sections.get('balance_summary', {})
                results_summary_data_ext = extracted_sections.get('results_summary', {})
                summary_save_attempted = False
                summary_save_ok = True 

                should_save_summary_now = True
                if is_duplicate_file_found and not any_new_transactional_data_added: # File-level duplicate AND no new transactions
                    st.info(f"({WORKSHEET_STATEMENT_SUMMARIES}) ข้ามการบันทึก Summary เนื่องจากไฟล์นี้เป็นไฟล์ซ้ำที่เคยประมวลผลสำเร็จแล้ว และไม่พบข้อมูล Deals/Orders/Positions ใหม่จากการประมวลผลไฟล์ครั้งนี้")
                    save_results_details['Summary'] = {'ok': True, 'status': 'skipped_duplicate_file_no_new_transactions', 'notes': "Summary: Skipped (duplicate file with no new transactional data)."}
                    should_save_summary_now = False
                
                if should_save_summary_now:
                    if balance_summary or results_summary_data_ext:
                        summary_save_attempted = True
                        summary_ok = save_results_summary_to_gsheets( # This function now returns only True/False
                            ws_dict[WORKSHEET_STATEMENT_SUMMARIES], balance_summary, results_summary_data_ext, 
                            active_portfolio_id_for_actual, active_portfolio_name_for_actual, 
                            file_name_for_saving, import_batch_id
                        )
                        # The st.info for skipping due to content duplicate is now INSIDE save_results_summary_to_gsheets
                        save_results_details['Summary'] = {'ok': summary_ok, 'status': 'processed', 'notes': f"Summary: Processed, Success={summary_ok}"}
                        if summary_ok: 
                             # Check if it was truly appended or skipped by content deduplication (which still returns True from save_results_summary_to_gsheets)
                             # This requires save_results_summary_to_gsheets to return more info, or we infer from messages.
                             # For now, if it's ok, we assume it was either appended or intentionally skipped by content check.
                             if not (is_duplicate_file_found and not any_new_transactional_data_added): # Only show "ดำเนินการสำเร็จ" if it wasn't skipped by outer logic
                                st.write(f"✔️ ({WORKSHEET_STATEMENT_SUMMARIES}) Summary Data: ดำเนินการสำเร็จ")
                        else: 
                            st.error(f"❌ ({WORKSHEET_STATEMENT_SUMMARIES}) Summary Data: การบันทึกล้มเหลว")
                        summary_save_ok = summary_ok
                    else: 
                        save_results_details['Summary'] = {'ok': True, 'status': 'no_data_to_save', 'notes': "Summary: No data in file to save."}
                
                if summary_save_attempted and not summary_save_ok: 
                    overall_processing_successful = False

                if overall_processing_successful:
                    if any_new_transactional_data_added or (save_results_details.get('Summary', {}).get('ok') and save_results_details.get('Summary',{}).get('status') != 'skipped_duplicate_file_no_new_transactions' and save_results_details.get('Summary',{}).get('status') != 'no_data_to_save'):
                        st.balloons(); st.success("ประมวลผลไฟล์สำเร็จและมีการเพิ่มข้อมูลใหม่!")
                    elif is_duplicate_file_found and not any_new_transactional_data_added and not should_save_summary_now: 
                        st.info(f"ไฟล์ '{file_name_for_saving}' เป็นไฟล์ซ้ำ และไม่พบรายการข้อมูลใหม่ (รวมถึง Summary ที่ถูกข้ามไป)")
                    else: st.info("ประมวลผลไฟล์สำเร็จ แต่ไม่พบข้อมูลใหม่ที่จะเพิ่ม")
        
        except UnicodeDecodeError as e_decode_main:
            st.error(f"เกิดข้อผิดพลาดในการ Decode ไฟล์หลัก: {e_decode_main}.")
            overall_processing_successful = False; save_results_details['MainError'] = {'ok': False, 'notes': f"UnicodeDecodeError: {e_decode_main}"}
        except gspread.exceptions.APIError as e_api_main: 
            st.error(f"❌ Google Sheets API Error (Main Processing): {e_api_main}.")
            overall_processing_successful = False; save_results_details['MainError'] = {'ok': False, 'notes': f"APIError: {e_api_main}"}
        except Exception as e_main:
            st.error(f"เกิดข้อผิดพลาดระหว่างประมวลผลหลัก: {type(e_main).__name__} - {str(e_main)[:200]}...")
            overall_processing_successful = False; save_results_details['MainError'] = {'ok': False, 'notes': f"MainError: {type(e_main).__name__} - {str(e_main)[:100]}"}
        
        final_processing_notes_list = [res.get('notes', '') for res in save_results_details.values() if res.get('notes')]
        final_notes_str = " | ".join(filter(None, final_processing_notes_list))[:49999] if final_processing_notes_list else "Processing complete."

        final_status = "Failed" 
        if overall_processing_successful:
            if any_new_transactional_data_added or (save_results_details.get('Summary', {}).get('ok') and save_results_details.get('Summary',{}).get('status') != 'skipped_duplicate_file_no_new_transactions' and save_results_details.get('Summary',{}).get('status') != 'no_data_to_save'):
                 final_status = "Success"
            elif is_duplicate_file_found and not any_new_transactional_data_added and save_results_details.get('Summary', {}).get('status') == 'skipped_duplicate_file_no_new_transactions': 
                final_status = "Success_DuplicateFile_NoNewRecords"
            else: final_status = "Success_NoNewRecords"
        
        try:
            history_rows_for_update = ws_dict[WORKSHEET_UPLOAD_HISTORY].get_all_values() 
            row_to_update_idx = None
            for idx_update, row_val_update in reversed(list(enumerate(history_rows_for_update))):
                if len(row_val_update) > 7 and row_val_update[7] == import_batch_id: 
                    row_to_update_idx = idx_update + 1; break
            
            if row_to_update_idx:
                ws_dict[WORKSHEET_UPLOAD_HISTORY].batch_update([
                    {'range': f'G{row_to_update_idx}', 'values': [[final_status]]},      
                    {'range': f'I{row_to_update_idx}', 'values': [[final_notes_str]]} 
                ], value_input_option='USER_ENTERED')
                st.info(f"อัปเดตสถานะ ImportBatchID '{import_batch_id}' เป็น '{final_status}' ใน {WORKSHEET_UPLOAD_HISTORY}")
            else: st.warning(f"ไม่พบ ImportBatchID '{import_batch_id}' ใน {WORKSHEET_UPLOAD_HISTORY} เพื่ออัปเดตสถานะสุดท้าย.")
        except Exception as e_update_hist: st.warning(f"ไม่สามารถอัปเดตสถานะสุดท้ายใน {WORKSHEET_UPLOAD_HISTORY} ({import_batch_id}): {e_update_hist}")
    else: 
        if uploaded_file_statement is not None: pass 
    st.markdown("---")
