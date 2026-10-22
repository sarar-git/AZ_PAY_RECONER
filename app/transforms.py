import io
import numpy as np
import pandas as pd
from openpyxl.styles import Alignment, Border, Side
from .balance import build_balance_sheet

ORDER_LEVEL_FEE_DESCRIPTIONS = [
    'Amazon Easy Ship Charges',
    'MFNPostagePurchaseCompleteIGST',
    'Amazon Easy Ship Weight Handling Fee Reversal',
    'Amazon Easy Ship Weight Handling Fee Reversal IGST',
    'Amazon Easy Ship Weight Handling Fee Reversal CGST',
    'Amazon Easy Ship Weight Handling Fee Reversal SGST',
    'FBA Weight Handling Fee',
    'FBA Weight Handling Fee CGST',
    'FBA Weight Handling Fee SGST',
    'FBA Weight Handling Fee IGST',
    'TechnologyFee',
    'TechnologyFee IGST',
    'TechnologyFee CGST',
    'TechnologyFee SGST',
]


def build_pay_sheet(settlements_df, reserves_df):
    if settlements_df.empty:
        return pd.DataFrame(columns=['Type', 'settlement-id', 'settlement-start-date', 'settlement-end-date', 'deposit-date', 'total-amount'])

    # Normalize reserve schema in case upstream provided an empty/malformed frame
    reserve_cols = ['type', 'start_date', 'end_date', 'prev_reserve', 'curr_reserve']
    reserves_df = reserves_df.copy() if reserves_df is not None else pd.DataFrame()
    for c in reserve_cols:
        if c not in reserves_df.columns:
            reserves_df[c] = pd.NA

    rows = []
    for _, s in settlements_df.iterrows():
        r = reserves_df[(reserves_df['type'] == s['type']) & (reserves_df['start_date'] == s['start_date']) & (reserves_df['end_date'] == s['end_date'])]
        prev = float(r['prev_reserve'].sum()) if not r.empty else 0.0
        curr = float(r['curr_reserve'].sum()) if not r.empty else 0.0
        rows.append({
            'Type': s['type'],
            'settlement-id': s['settlement_id'],
            'settlement-start-date': s['start_date'],
            'settlement-end-date': s['end_date'],
            'deposit-date': s['deposit_date'],
            'total-amount': float(s['total_amount']),
            'currency': s.get('currency', None),
            'COD_OPENING_AMOUNT': prev if s['type'] == 'COD' else 0.0,
            'NCOD_OPENING_AMOUNT': prev if s['type'] == 'NCOD' else 0.0,
            'TOTAL_OPENING_AMOUNT': prev,
            'COD_CLOSING_RESERVE': curr if s['type'] == 'COD' else 0.0,
            'NCOD_CLOSING_RESERVE': curr if s['type'] == 'NCOD' else 0.0,
            'TOTAL_CLOSING_RESERVE': curr,
        })
    pay_df = pd.DataFrame(rows).sort_values('deposit-date')
    total = {c: np.nan for c in pay_df.columns}
    total['total-amount'] = pay_df['total-amount'].sum()
    return pd.concat([pay_df, pd.DataFrame([total])], ignore_index=True)


def build_orders_sheet(transactions):
    orders = transactions[transactions['transaction_type'] == 'Order'].copy()
    if orders.empty:
        cols = ['order-id', 'sku', 'quantity-purchased', 'Final Paid Amount']
        return pd.DataFrame(columns=cols)

    p = pd.pivot_table(
        orders,
        values='amount',
        index=['order_id', 'sku', 'quantity'],
        columns='amount_description',
        aggfunc='sum',
        fill_value=0,
    ).reset_index()
    p = p.rename(columns={'order_id': 'order-id', 'quantity': 'quantity-purchased'})

    # Map order-level FBA/Technology fees into ORDERS and distribute across SKUs per order-id
    fee_rows = transactions[transactions['amount_description'].isin(ORDER_LEVEL_FEE_DESCRIPTIONS)].copy()
    if not fee_rows.empty:
        fee_pivot = pd.pivot_table(
            fee_rows,
            values='amount',
            index='order_id',
            columns='amount_description',
            aggfunc='sum',
            fill_value=0,
        )

        existing_order_ids = set(p['order-id'].dropna().unique())
        fee_order_ids = set(fee_pivot.index)
        missing_order_ids = fee_order_ids - existing_order_ids

        if missing_order_ids:
            orphan_rows = [{'order-id': oid, 'sku': 'FEE-ONLY-NO-ORDER', 'quantity-purchased': 0} for oid in missing_order_ids]
            p = pd.concat([p, pd.DataFrame(orphan_rows)], ignore_index=True)

        for col in ORDER_LEVEL_FEE_DESCRIPTIONS:
            if col not in p.columns:
                p[col] = 0.0

        sku_count = p.groupby('order-id').size()
        for idx, row in p.iterrows():
            oid = row['order-id']
            if oid in fee_pivot.index:
                divisor = sku_count.get(oid, 1) or 1
                for col in ORDER_LEVEL_FEE_DESCRIPTIONS:
                    if col in fee_pivot.columns:
                        p.at[idx, col] = float(fee_pivot.loc[oid, col]) / divisor

    p['Final Paid Amount'] = p.select_dtypes(include='number').drop(columns=['quantity-purchased'], errors='ignore').sum(axis=1)
    total = {c: np.nan for c in p.columns}
    for c in p.select_dtypes(include='number').columns:
        if c != 'quantity-purchased':
            total[c] = p[c].sum()
    return pd.concat([p, pd.DataFrame([total])], ignore_index=True)


def build_refunds_sheet(transactions, orders_df):
    refunds = transactions[transactions['transaction_type'] == 'Refund'].copy()
    if refunds.empty:
        return pd.DataFrame(columns=['order-id', 'sku', 'quantity-purchased', 'Grand Total'])
    p = pd.pivot_table(refunds, values='amount', index=['order_id', 'sku', 'quantity'], columns='amount_description', aggfunc='sum', fill_value=0).reset_index()
    p = p.rename(columns={'order_id': 'order-id', 'quantity': 'quantity-purchased'})
    qty_lookup = {(r['order-id'], r['sku']): r['quantity-purchased'] for _, r in orders_df.iloc[:-1].iterrows()} if len(orders_df) > 0 else {}
    for i, r in p.iterrows():
        p.at[i, 'quantity-purchased'] = qty_lookup.get((r['order-id'], r['sku']), r['quantity-purchased'])
    p['Grand Total'] = p.select_dtypes(include='number').drop(columns=['quantity-purchased'], errors='ignore').sum(axis=1)
    total = {c: np.nan for c in p.columns}
    for c in p.select_dtypes(include='number').columns:
        if c != 'quantity-purchased':
            total[c] = p[c].sum()
    return pd.concat([p, pd.DataFrame([total])], ignore_index=True)


def build_others_sheet(transactions):
    exclude = {'Previous Reserve Amount Balance', 'Current Reserve Amount', *ORDER_LEVEL_FEE_DESCRIPTIONS}
    others = transactions[(~transactions['transaction_type'].isin(['Order', 'Refund', ''])) & (~transactions['amount_description'].isin(exclude))].copy()
    cols = ['type', 'settlement_id', 'order_id', 'amount_description', 'sku', 'quantity', 'amount']
    for c in cols:
        if c not in others.columns:
            others[c] = np.nan
    out = others[cols].rename(columns={'type': 'Type', 'settlement_id': 'settlement-id', 'order_id': 'order-id', 'amount_description': 'amount-description', 'quantity': 'quantity-purchased'})
    total = {c: np.nan for c in out.columns}
    total['amount'] = out['amount'].sum() if not out.empty else 0.0
    return pd.concat([out, pd.DataFrame([total])], ignore_index=True)


def build_bill_sheet(orders_df, refunds_df):
    if orders_df.empty:
        return pd.DataFrame(columns=['SKU', 'QTY SENT', 'QTY RETURNED', 'FINAL QTY', 'FINAL PAID AMOUNT', 'AVERAGE PAYOUT'])
    o = orders_df.iloc[:-1].groupby('sku').agg({'quantity-purchased': 'sum', 'Final Paid Amount': 'sum'}).reset_index()
    o.columns = ['SKU', 'QTY SENT', 'Order_Payout']
    if not refunds_df.empty and len(refunds_df) > 1:
        r = refunds_df.iloc[:-1].groupby('sku').agg({'quantity-purchased': 'sum', 'Grand Total': 'sum'}).reset_index()
        r.columns = ['SKU', 'QTY RETURNED', 'Refund_Amount']
    else:
        r = pd.DataFrame(columns=['SKU', 'QTY RETURNED', 'Refund_Amount'])
    b = o.merge(r, on='SKU', how='left').fillna({'QTY RETURNED': 0, 'Refund_Amount': 0})
    b['FINAL QTY'] = b['QTY SENT'] - b['QTY RETURNED']
    b['FINAL PAID AMOUNT'] = b['Order_Payout'] + b['Refund_Amount']
    b['AVERAGE PAYOUT'] = b.apply(lambda x: x['FINAL PAID AMOUNT'] / x['FINAL QTY'] if x['FINAL QTY'] else 0, axis=1)
    out = b[['SKU', 'QTY SENT', 'QTY RETURNED', 'FINAL QTY', 'FINAL PAID AMOUNT', 'AVERAGE PAYOUT']]
    total = {'SKU': 'GRAND TOTAL', 'QTY SENT': out['QTY SENT'].sum(), 'QTY RETURNED': out['QTY RETURNED'].sum(), 'FINAL QTY': out['FINAL QTY'].sum(), 'FINAL PAID AMOUNT': out['FINAL PAID AMOUNT'].sum()}
    total['AVERAGE PAYOUT'] = total['FINAL PAID AMOUNT'] / total['FINAL QTY'] if total['FINAL QTY'] else 0
    return pd.concat([out, pd.DataFrame([total])], ignore_index=True)


def apply_excel_formatting(writer, sheet_name):
    ws = writer.sheets[sheet_name]
    border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
    align = Alignment(horizontal='left', vertical='top', wrap_text=False)
    for row in ws.iter_rows():
        for c in row:
            c.border = border
            c.alignment = align
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = min(max(len(str(x.value)) if x.value is not None else 0 for x in col) + 2, 50)


def generate_excel(transactions, settlements_df, reserves_df):
    pay = build_pay_sheet(settlements_df, reserves_df)
    orders = build_orders_sheet(transactions)
    refunds = build_refunds_sheet(transactions, orders)
    others = build_others_sheet(transactions)
    bill = build_bill_sheet(orders, refunds)
    balance = build_balance_sheet(pay, orders, refunds, others, reserves_df)

    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as w:
        pay.to_excel(excel_writer=w, sheet_name='PAY', index=False)
        orders.to_excel(excel_writer=w, sheet_name='ORDERS', index=False)
        refunds.to_excel(excel_writer=w, sheet_name='REFUNDS', index=False)
        others.to_excel(excel_writer=w, sheet_name='OTHERS', index=False)
        bill.to_excel(excel_writer=w, sheet_name='BILL', index=False)
        balance.to_excel(excel_writer=w, sheet_name='BALANCE_SHEET', index=False, header=False)
        for s in ['PAY', 'ORDERS', 'REFUNDS', 'OTHERS', 'BILL', 'BALANCE_SHEET']:
            apply_excel_formatting(w, s)
    out.seek(0)
    return out
