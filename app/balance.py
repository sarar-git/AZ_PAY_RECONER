import warnings
import numpy as np
import pandas as pd


KNOWN_DT_FORMATS = [
    '%d.%m.%Y %H:%M:%S %Z',
    '%Y-%m-%d %H:%M:%S%z',
    '%Y-%m-%d %H:%M:%S',
    '%Y-%m-%d',
]


def _to_date_only(series: pd.Series) -> pd.Series:
    """Parse mixed settlement date strings into date values without parser warnings."""
    parsed = pd.Series(pd.NaT, index=series.index, dtype='datetime64[ns, UTC]')

    for fmt in KNOWN_DT_FORMATS:
        mask = parsed.isna() & series.notna()
        if not mask.any():
            break
        parsed.loc[mask] = pd.to_datetime(series.loc[mask], format=fmt, errors='coerce', utc=True)

    # final fallback for unexpected formats; dayfirst handles DD.MM.YYYY style values
    mask = parsed.isna() & series.notna()
    if mask.any():
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', message='Parsing dates in .* dayfirst=False .*')
            parsed.loc[mask] = pd.to_datetime(series.loc[mask], errors='coerce', dayfirst=True, utc=True)

    return parsed.dt.date


def build_balance_sheet(pay_df, orders_df, refunds_df, others_df, reserves_df):
    total_deposits = float(pay_df.iloc[-1]['total-amount']) if not pay_df.empty else 0.0
    orders_total = float(orders_df.iloc[-1].get('Final Paid Amount', 0)) if not orders_df.empty else 0.0
    refunds_total = float(refunds_df.iloc[-1].get('Grand Total', 0)) if not refunds_df.empty else 0.0
    others_total = float(others_df.iloc[-1].get('amount', 0)) if not others_df.empty else 0.0

    if reserves_df.empty:
        oldest_opening_total = 0.0
        latest_closing_total = 0.0
    else:
        r = reserves_df.copy()
        r['start_date_only'] = _to_date_only(r['start_date'])
        r['end_date_only'] = _to_date_only(r['end_date'])

        valid_start_dates = r['start_date_only'].dropna()
        valid_end_dates = r['end_date_only'].dropna()

        oldest = valid_start_dates.min() if not valid_start_dates.empty else None
        latest = valid_end_dates.max() if not valid_end_dates.empty else None

        oldest_opening_total = (
            r[r['start_date_only'] == oldest]['prev_reserve'].fillna(0).sum()
            if oldest is not None
            else 0.0
        )
        latest_closing_total = (
            r[r['end_date_only'] == latest]['curr_reserve'].fillna(0).sum()
            if latest is not None
            else 0.0
        )

    left_net = total_deposits - oldest_opening_total + latest_closing_total
    right_net = orders_total + refunds_total + others_total
    diff = round(left_net - right_net, 2)

    return pd.DataFrame({
        'LEFT_DESC': ['TOTAL AMOUNT DEPOSITED IN BANK', 'LESS: OLDEST OPENING RESERVE (COD + NCOD)',
                      'ADD: LATEST CLOSING RESERVE (COD + NCOD)', 'NET RECONCILED AMOUNT', 'DIFFERENCE (LEFT - RIGHT)'],
        'LEFT_AMT': [total_deposits, -oldest_opening_total, latest_closing_total, left_net, diff],
        'SPACER1': [np.nan] * 5,
        'SPACER2': [np.nan] * 5,
        'SPACER3': [np.nan] * 5,
        'RIGHT_DESC': ['TOTAL ORDERS AMOUNT', 'TOTAL REFUNDS AMOUNT', 'TOTAL OTHERS AMOUNT', 'NET RECONCILED AMOUNT', ''],
        'RIGHT_AMT': [orders_total, refunds_total, others_total, right_net, ''],
    })
