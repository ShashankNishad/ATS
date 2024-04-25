import streamlit as st
import pandas as pd
import hashlib
import random
from datetime import datetime

import firebase_admin
from firebase_admin import credentials, db

# Check if the Firebase app is already initialized
if not firebase_admin._apps:
    cred = credentials.Certificate("operationats-f3fcf-6d04f307a5f5.json")
    firebase_admin.initialize_app(cred, name='order-management', options={
        'databaseURL': 'https://operationats-f3fcf-default-rtdb.firebaseio.com/'
    })

# Define a function to generate session state
def get_session_id():
    return hashlib.sha256(str(st.session_state).encode()).hexdigest()

# Define a function to create or get session state
def create_or_get_session_state():
    session_id = get_session_id()
    if not hasattr(st, '_custom_session_state'):
        st._custom_session_state = {}
    if session_id not in st._custom_session_state:
        st._custom_session_state[session_id] = SessionState(_counter=0)
    return st._custom_session_state[session_id]

# Define the SessionState class
class SessionState(object):
    def __init__(self, **kwargs):
        for key, val in kwargs.items():
            setattr(self, key, val)

@st.cache_data
def read_order_data():
    ref = db.reference('orders')
    orders = ref.get()
    if orders:
        existing_df = pd.DataFrame.from_dict(orders, orient='index')
        existing_df["Order Date"] = pd.to_datetime(existing_df["Order Date"]).dt.strftime('%Y-%m-%d')
        existing_df["Delivery Date"] = pd.to_datetime(existing_df["Delivery Date"]).dt.strftime('%Y-%m-%d')
        return existing_df
    else:
        return pd.DataFrame()

def update_transaction_log(order_number, column, old_value, new_value):
    ref = db.reference(f'logs/{order_number}')
    log_data = {
        "Date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "Order Number": order_number,
        "Column": column,
        "Old Value": old_value,
        "New Value": new_value
    }
    ref.push(log_data)

def generate_order_number():
    return random.randint(10**6, 10**9)

def create_order():
    order_number = generate_order_number()
    emp_id = st.text_input("Employee ID")
    customer_name = st.text_input("Customer Name")
    contact_number = st.text_input("Contact Number")
    order_date = st.date_input("Order Date")
    delivery_date = st.date_input("Delivery Date")
    product_id = st.text_input("Product ID")
    quantity = st.number_input("Quantity", min_value=0.0, step=0.01)
    price = st.number_input("Price", min_value=0)
    shop_name = st.text_input("Shop Name")
    location = st.text_input("Location")
    landmark = st.text_input("Landmark")
    remarks = st.text_area("Remarks")

    total_price = quantity * price

    if st.button("Save Order"):
        try:
            contact_number = int(contact_number) if contact_number else None
            order_data = {
                "Order Number": order_number,
                "Emp ID": emp_id,
                "Customer Name": customer_name,
                "Contact Number": contact_number,
                "Order Date": order_date.strftime('%Y-%m-%d'),
                "Delivery Date": delivery_date.strftime('%Y-%m-%d'),
                "Product ID": product_id,
                "Quantity": quantity,
                "Price": price,
                "Total Price": total_price,
                "Shop Name": shop_name,
                "Location": location,
                "Landmark": landmark,
                "Remarks": remarks
            }

            ref = db.reference('orders')
            ref.child(str(order_number)).set(order_data)

            st.success("Order saved successfully!")
        except ValueError:
            st.error("Contact Number must be an integer.")
        except Exception as e:
            st.error(f"An error occurred while saving the order: {e}")

def delivery_update():
    contact_number = st.text_input("Enter Contact Number")

    if contact_number:
        order_df = read_order_data()

        contact_number = int(contact_number)

        # Check if the column exists in the DataFrame
        if "Contact Number" in order_df.columns:
            # Use the column name as it is
            contact_column = "Contact Number"
        elif "Customer Phone" in order_df.columns:
            # Use alternative column name if available
            contact_column = "Customer Phone"
        else:
            st.error("Contact Number column not found in records!")
            st.write("Available columns:", order_df.columns.tolist())
            return

        matching_rows = order_df[order_df[contact_column] == contact_number]

        if not matching_rows.empty:
            st.write("Matching Rows:")
            st.write(matching_rows)

            order_number = st.number_input("Enter the Order Number to update", min_value=matching_rows["Order Number"].min(), max_value=matching_rows["Order Number"].max())

            if order_number in matching_rows["Order Number"].values:
                row = matching_rows[matching_rows["Order Number"] == order_number].iloc[0]

                amount_received = st.number_input(f"Enter Amount Received for Order Number {order_number}", value=row.get("Amount Received", 0))
                payment_status = st.selectbox(f"Payment Status for Order Number {order_number}", ["Online", "Cash"], index=0 if row.get("Payment Status") == "Online" else 1)
                delivery_status = st.selectbox(f"Delivery Status for Order Number {order_number}", ["Done", "Pending", "Cancel", "Full Payment", "Half Payment"], index=0 if row.get("Delivery Status") == "Done" else 1)

                if st.button(f"Save/Update for Order Number {order_number}"):
                    # Update the delivery status and product in the DataFrame
                    old_amount = row.get("Amount Received", 0)
                    old_delivery_status = row.get("Delivery Status")
                    old_payment_status = row.get("Payment Status")

                    order_data = {
                        "Amount Received": amount_received,
                        "Payment Status": payment_status,
                        "Delivery Status": delivery_status
                    }

                    ref = db.reference('orders')
                    ref.child(str(order_number)).update(order_data)

                    # Log the transaction
                    update_transaction_log(order_number, "Amount Received", old_amount, amount_received)
                    update_transaction_log(order_number, "Payment Status", old_payment_status, payment_status)
                    update_transaction_log(order_number, "Delivery Status", old_delivery_status, delivery_status)

                    st.success("Delivery status and product updated successfully!")
            else:
                st.error(f"Order Number {order_number} not found for the entered Contact Number!")
        else:
            st.error("Contact Number not found in records!")

def payment_and_pending():
    emp_id = st.text_input("Enter Employee ID")

    if emp_id:
        try:
            order_df = read_order_data()

            # Date range selector
            start_date = st.date_input("Start Date")
            end_date = st.date_input("End Date", value=pd.Timestamp.now()).strftime('%Y-%m-%d')

            # Convert to datetime64[ns]
            start_date = pd.to_datetime(start_date)
            end_date = pd.to_datetime(end_date)

            # Filter the DataFrame based on the selected date range
            filtered_df = order_df[(order_df["Emp ID"] == emp_id) & 
                                   (pd.to_datetime(order_df["Order Date"]) >= start_date) & 
                                   (pd.to_datetime(order_df["Order Date"]) <= end_date)]

            if not filtered_df.empty:
                st.write("Data with Pending Amount:")
                st.write(filtered_df)
            else:
                st.warning(f"No data found for Employee ID: {emp_id}")
        except FileNotFoundError:
            st.error("File not found!")

def view_transaction_logs():
    logs_ref = db.reference('logs')
    logs = logs_ref.get()

    if logs:
        st.write("Transaction Logs:")
        log_list = [log for log in logs.values()]
        log_df = pd.DataFrame(log_list)
        st.write(log_df)
    else:
        st.info("No transaction logs available.")

def main():
    st.title("Order Management System")

    options = {
        "PO Form": create_order,
        "Delivery Updates": delivery_update,
        "Payment and Pending": payment_and_pending,
        "View Transaction Logs": view_transaction_logs
    }

    selection = st.sidebar.radio("Select Functionality", list(options.keys()))

    options[selection]()

if __name__ == "__main__":
    main()