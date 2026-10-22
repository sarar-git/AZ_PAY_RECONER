#!/usr/bin/env python3
"""
Complete Amazon Payment Reconciliation System
Processes TSV files and generates single Excel file with all sheets:
- PAY Sheet
- ORDERS Sheet  
- REFUNDS Sheet
- OTHERS Sheet
- BILL Sheet
- BALANCE_SHEET (boundary reserves logic)
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys


# ----------------------------
# Utilities
# ----------------------------
def extract_type_from_filename(filename):
    filename_lower = filename.lower()
    if 'ncod' in filename_lower:
        return 'NCOD'
    if 'cod' in filename_lower:
        return 'COD'
    raise ValueError(f"Cannot determine payment type from filename: {filename}")


# ----------------------------
# PAY Sheet
# ----------------------------
def build_pay_sheet(tsv_files):
    """Build PAY sheet with settlement summaries (opening + closing reserves for COD & NCOD)"""
    settlements = []

    for filepath in tsv_files:
        df = pd.read_csv(filepath, sep='\t')
        filename = Path(filepath).name
        settlement_type = extract_type_from_filename(filename)

        first_row = df.iloc[0]

        prev_rows = df[df['amount-description'] == 'Previous Reserve Amount Balance']
        curr_rows = df[df['amount-description'] == 'Current Reserve Amount']

        prev_reserve_amt = float(prev_rows.iloc[0]['amount']) if len(prev_rows) else 0.0
        curr_reserve_amt = float(curr_rows.iloc[0]['amount']) if len(curr_rows) else 0.0

        settlement = {
            'Type': settlement_type,
            'settlement-id': first_row['settlement-id'],
            'settlement-start-date': first_row['settlement-start-date'],
            'settlement-end-date': first_row['settlement-end-date'],
            'deposit-date': first_row['deposit-date'],
            'total-amount': float(first_row['total-amount']),
            'currency': first_row['currency'],

            'COD_OPENING_AMOUNT': abs(prev_reserve_amt) if settlement_type == 'COD' else 0.0,
            'NCOD_OPENING_AMOUNT': abs(prev_reserve_amt) if settlement_type == 'NCOD' else 0.0,
            'TOTAL_OPENING_AMOUNT': abs(prev_reserve_amt),

            'COD_CLOSING_RESERVE': abs(curr_reserve_amt) if settlement_type == 'COD' else 0.0,
            'NCOD_CLOSING_RESERVE': abs(curr_reserve_amt) if settlement_type == 'NCOD' else 0.0,
            'TOTAL_CLOSING_RESERVE': abs(curr_reserve_amt),
        }

        settlements.append(settlement)

    pay_df = pd.DataFrame(settlements).sort_values('deposit-date')

    total_row = pd.DataFrame([{
        'Type': np.nan,
        'settlement-id': np.nan,
        'settlement-start-date': np.nan,
        'settlement-end-date': np.nan,
        'deposit-date': np.nan,
        'total-amount': pay_df['total-amount'].sum(),
        'currency': np.nan,
        'COD_OPENING_AMOUNT': np.nan,
        'NCOD_OPENING_AMOUNT': np.nan,
        'TOTAL_OPENING_AMOUNT': np.nan,
        'COD_CLOSING_RESERVE': np.nan,
        'NCOD_CLOSING_RESERVE': np.nan,
        'TOTAL_CLOSING_RESERVE': np.nan,
    }])

    return pd.concat([pay_df, total_row], ignore_index=True)


# ----------------------------
# Reserve Summary (for BALANCE)
# ----------------------------
def build_reserve_summary(tsv_files):
    rows = []

    for filepath in tsv_files:
        df = pd.read_csv(filepath, sep='\t')
        pay_type = extract_type_from_filename(Path(filepath).name)
        first_row = df.iloc[0]

        start_date = pd.to_datetime(first_row['settlement-start-date'], utc=True, dayfirst=True, errors='coerce')
        end_date = pd.to_datetime(first_row['settlement-end-date'], utc=True, dayfirst=True, errors='coerce')

        prev_rows = df[df['amount-description'] == 'Previous Reserve Amount Balance']
        curr_rows = df[df['amount-description'] == 'Current Reserve Amount']

        prev_amt = float(prev_rows.iloc[0]['amount']) if len(prev_rows) else 0.0
        curr_amt = float(curr_rows.iloc[0]['amount']) if len(curr_rows) else 0.0

        rows.append({
            'Type': pay_type,
            'start_date': start_date,
            'end_date': end_date,
            'prev_reserve': abs(prev_amt),
            'curr_reserve': abs(curr_amt),
        })

    return pd.DataFrame(rows)


# ----------------------------
# BALANCE SHEET (Boundary Logic)
# ----------------------------
def build_balance_sheet(pay_df, orders_df, refunds_df, others_df, reserve_df):
    print("Building BALANCE_SHEET (boundary reserves logic)...")

    total_deposits = pay_df.iloc[-1]['total-amount']
    orders_total = orders_df.iloc[-1]['Final Paid Amount']
    refunds_total = refunds_df.iloc[-1]['Grand Total']
    others_total = others_df.iloc[-1]['amount']

   # Normalize to date only (ignore time)
    reserve_df['start_date_only'] = reserve_df['start_date'].dt.date
    reserve_df['end_date_only'] = reserve_df['end_date'].dt.date
    
    # --- OLDEST OPENING RESERVE (GLOBAL DATE, IGNORE TIME) ---
    global_oldest_date = reserve_df['start_date_only'].min()
    oldest_rows = reserve_df[reserve_df['start_date_only'] == global_oldest_date]
    oldest_opening_total = oldest_rows['prev_reserve'].sum()
    
    # --- LATEST CLOSING RESERVE (GLOBAL DATE, IGNORE TIME) ---
    global_latest_date = reserve_df['end_date_only'].max()
    latest_rows = reserve_df[reserve_df['end_date_only'] == global_latest_date]
    latest_closing_total = latest_rows['curr_reserve'].sum()



    left_net = total_deposits - oldest_opening_total + latest_closing_total
    right_net = orders_total + refunds_total + others_total
    diff = round(left_net - right_net, 2)
    
    return pd.DataFrame({
        'LEFT_DESC': [
            'TOTAL AMOUNT DEPOSITED IN BANK',
            'LESS: OLDEST OPENING RESERVE (COD + NCOD)',
            'ADD: LATEST CLOSING RESERVE (COD + NCOD)',
            'NET RECONCILED AMOUNT',
            'DIFFERENCE (LEFT - RIGHT)'
        ],
        'LEFT_AMT': [
            total_deposits,
            -oldest_opening_total,
            latest_closing_total,   # ADD back
            left_net,
            diff
        ],

        'SPACER1': [np.nan] * 5,
        'SPACER2': [np.nan] * 5,
        'SPACER3': [np.nan] * 5,
        'RIGHT_DESC': [
            'TOTAL ORDERS AMOUNT',
            'TOTAL REFUNDS AMOUNT',
            'TOTAL OTHERS AMOUNT',
            'NET RECONCILED AMOUNT',
            ''
        ],
        'RIGHT_AMT': [
            orders_total,
            refunds_total,
            others_total,
            right_net,
            ''
        ]
    })


# =========================
# Existing functions remain unchanged:
# build_orders_sheet
# build_refunds_sheet
# build_others_sheet
# build_bill_sheet
# apply_excel_formatting
# =========================

def process_tsv_files(tsv_files, output_file):
    print("\n" + "="*80)
    print("AMAZON PAYMENT RECONCILIATION - COMPLETE PROCESSOR")
    print("="*80)

    pay_df = build_pay_sheet(tsv_files)
    orders_df = build_orders_sheet(tsv_files)
    refunds_df = build_refunds_sheet(tsv_files, orders_df)
    others_df = build_others_sheet(tsv_files)
    bill_df = build_bill_sheet(orders_df, refunds_df)

    reserve_df = build_reserve_summary(tsv_files)
    balance_df = build_balance_sheet(pay_df, orders_df, refunds_df, others_df, reserve_df)

    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        pay_df.to_excel(writer, sheet_name='PAY', index=False)
        orders_df.to_excel(writer, sheet_name='ORDERS', index=False)
        refunds_df.to_excel(writer, sheet_name='REFUNDS', index=False)
        others_df.to_excel(writer, sheet_name='OTHERS', index=False)
        bill_df.to_excel(writer, sheet_name='BILL', index=False)
        balance_df.to_excel(writer, sheet_name='BALANCE_SHEET', index=False, header=False)

        apply_excel_formatting(writer, 'PAY', pay_df)
        apply_excel_formatting(writer, 'ORDERS', orders_df)
        apply_excel_formatting(writer, 'REFUNDS', refunds_df)
        apply_excel_formatting(writer, 'OTHERS', others_df)
        apply_excel_formatting(writer, 'BILL', bill_df)
        apply_excel_formatting(writer, 'BALANCE_SHEET', balance_df)

    print(f"\n✅ Complete! Output saved to: {output_file}")
    return output_file


def main():
    if len(sys.argv) < 2:
        print("Usage: python amazon_reconciliation_complete.py <tsv_file1> <tsv_file2> ...")
        sys.exit(1)

    tsv_files = sys.argv[1:]
    for f in tsv_files:
        if not Path(f).exists():
            print(f"Error: File not found: {f}")
            sys.exit(1)

    process_tsv_files(tsv_files, 'Amazon_Payment_Reconciliation_Complete.xlsx')


if __name__ == '__main__':
    main()
