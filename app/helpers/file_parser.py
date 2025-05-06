from datetime import timedelta

import pandas as pd


def parse_excel(file_path):
    required_cols = [
        "Base Address", "Shipping Address", "Starting Time",
        "Expected Delivery Time (hours)", "Actual Delivery Time (hours)",
        "Expected Delivery Cost (VND)", "Actual Delivery Cost (VND)",
        "Max Delivery Cost (VND/hr)"
    ]
    result = {"inefficient_routes": []}
    try:
        xls = pd.ExcelFile(file_path)
        for sheet in xls.sheet_names:
            df = xls.parse(sheet)
            df.columns = df.columns.str.strip()
            if not set(required_cols).issubset(df.columns):
                continue
            for _, row in df.iterrows():
                if any(pd.isnull(row[col]) for col in required_cols):
                    continue
                st = row["Starting Time"]
                exp_hours = to_float(row["Expected Delivery Time (hours)"])
                act_hours = to_float(row["Actual Delivery Time (hours)"])
                if exp_hours is None or act_hours is None:
                    continue
                diff = act_hours - exp_hours
                if diff > 24:
                    expected_dt = st + timedelta(hours=exp_hours)
                    actual_dt = st + timedelta(hours=act_hours)
                    ec = to_float(row["Expected Delivery Cost (VND)"])
                    ac = to_float(row["Actual Delivery Cost (VND)"])
                    mc = to_float(row["Max Delivery Cost (VND/hr)"])
                    if None in (ec, ac, mc):
                        continue
                    route = {
                        "base_address": str(row["Base Address"]),
                        "shipping_address": str(row["Shipping Address"]),
                        "starting_time": st,
                        "expected_delivery_time": expected_dt,
                        "actual_delivery_time": actual_dt,
                        "expected_delivery_cost": ec,
                        "actual_delivery_cost": ac,
                        "max_delivery_cost": mc,
                        "delay_hours": diff
                    }
                    result["inefficient_routes"].append(route)
        return result
    except Exception as e:
        print(f"Error processing Excel file: {e}")
        return result


def to_float(value):
    try:
        return float(str(value).replace(',', '').strip())
    except Exception:
        return None
