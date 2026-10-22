from pathlib import Path
import pandas as pd

CANON_COLS = [
    'settlement_id', 'start_date', 'end_date', 'deposit_date', 'type',
    'transaction_type', 'order_id', 'sku', 'quantity', 'amount_description', 'amount'
]

COL_MAP = {
    'settlement-id': 'settlement_id',
    'settlement-start-date': 'start_date',
    'settlement-end-date': 'end_date',
    'deposit-date': 'deposit_date',
    'transaction-type': 'transaction_type',
    'order-id': 'order_id',
    'sku': 'sku',
    'quantity-purchased': 'quantity',
    'amount-description': 'amount_description',
    'amount': 'amount',
}


def extract_type_from_filename(filename: str) -> str:
    n = filename.lower()
    if 'ncod' in n:
        return 'NCOD'
    if 'cod' in n:
        return 'COD'
    return 'UNKNOWN'


def _normalize_chunk(chunk: pd.DataFrame, pay_type: str) -> pd.DataFrame:
    rename = {c: COL_MAP[c] for c in chunk.columns if c in COL_MAP}
    c = chunk.rename(columns=rename).copy()
    for col in CANON_COLS:
        if col not in c.columns:
            c[col] = pd.NA
    c = c[CANON_COLS]
    c['type'] = pay_type
    c['transaction_type'] = c['transaction_type'].fillna('')
    c['amount_description'] = c['amount_description'].fillna('')
    c['amount'] = pd.to_numeric(c['amount'], errors='coerce').fillna(0.0)
    c['quantity'] = pd.to_numeric(c['quantity'], errors='coerce').fillna(0)
    return c


def ingest_tsv_files(paths):
    tx_chunks, settlements, reserves = [], [], []
    warnings = []

    for path in paths:
        p = Path(path)
        pay_type = extract_type_from_filename(p.name)
        saw_rows = False
        first_non_empty = None

        for chunk in pd.read_csv(path, sep='\t', chunksize=100_000, dtype=str):
            saw_rows = True
            if first_non_empty is None and not chunk.empty:
                first_non_empty = chunk.iloc[0]
            norm = _normalize_chunk(chunk, pay_type)
            tx_chunks.append(norm)

            reserve_rows = norm[norm['amount_description'].isin(['Previous Reserve Amount Balance', 'Current Reserve Amount'])]
            if not reserve_rows.empty:
                prev = reserve_rows.loc[reserve_rows['amount_description'] == 'Previous Reserve Amount Balance', 'amount'].sum()
                curr = reserve_rows.loc[reserve_rows['amount_description'] == 'Current Reserve Amount', 'amount'].sum()
                reserves.append({
                    'type': pay_type,
                    'start_date': norm['start_date'].dropna().iloc[0] if norm['start_date'].notna().any() else None,
                    'end_date': norm['end_date'].dropna().iloc[0] if norm['end_date'].notna().any() else None,
                    'prev_reserve': abs(float(prev)),
                    'curr_reserve': abs(float(curr)),
                })

        if not saw_rows:
            warnings.append(f'{p.name}: empty file')
            continue

        if first_non_empty is not None:
            settlements.append({
                'type': pay_type,
                'settlement_id': first_non_empty.get('settlement-id', None),
                'start_date': first_non_empty.get('settlement-start-date', None),
                'end_date': first_non_empty.get('settlement-end-date', None),
                'deposit_date': first_non_empty.get('deposit-date', None),
                'total_amount': float(first_non_empty.get('total-amount', 0) or 0),
                'currency': first_non_empty.get('currency', None),
            })

    transactions = pd.concat(tx_chunks, ignore_index=True) if tx_chunks else pd.DataFrame(columns=CANON_COLS)
    settlements_df = pd.DataFrame(settlements)
    reserves_df = pd.DataFrame(reserves)

    # Keep stable schemas even when no rows were captured
    if settlements_df.empty:
        settlements_df = pd.DataFrame(columns=['type', 'settlement_id', 'start_date', 'end_date', 'deposit_date', 'total_amount', 'currency'])
    if reserves_df.empty:
        reserves_df = pd.DataFrame(columns=['type', 'start_date', 'end_date', 'prev_reserve', 'curr_reserve'])

    return transactions, settlements_df, reserves_df, warnings
