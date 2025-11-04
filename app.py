import os
import uuid
import json
import requests
from datetime import datetime
from flask import Flask, render_template, request, jsonify

# --- Configuration and Database Initialization ---

app = Flask(__name__)

# 1. Load Secure Environment Variables
DATABASE_URL = os.environ.get('DATABASE_URL') 
DATABASE_AUTH_TOKEN = os.environ.get('DATABASE_AUTH_TOKEN')
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24).hex()) 

# Check for required credentials (Crucial for Vercel deployment)
if not DATABASE_URL or not DATABASE_AUTH_TOKEN:
    raise ValueError("FATAL: Database URL or Auth Token not set in Vercel Environment Variables.")

# 2. Turso HTTP API Setup
# Convert the libsql URL (e.g., libsql://...) to the HTTPS endpoint
API_URL = DATABASE_URL.replace("libsql://", "https://")

def execute_sql(sql_query, params=None):
    """Executes a single SQL query via the Turso HTTP API using requests."""
    
    statements = [{"q": sql_query}]

    try:
        headers = {
            "Authorization": f"Bearer {DATABASE_AUTH_TOKEN}",
            "Content-Type": "application/json"
        }
        
        # Send the query list to the Turso API endpoint
        response = requests.post(f"{API_URL}", headers=headers, json={"statements": statements}, timeout=10)
        response.raise_for_status() # Raises an HTTPError for bad responses (4xx or 5xx)
        
        data = response.json()
        
        if not data or not isinstance(data, list) or 'results' not in data[0]:
            # Check for errors in the Turso response structure
            if 'error' in data[0]:
                 raise RuntimeError(f"Turso SQL Error: {data[0]['error']}")
            
            # Simplified result for DDL/DML operations where result might be minimal
            return {"rows": [], "rows_affected": data[0].get('rows_affected', 0), "columns": []}

        result = data[0]['results'] # Access the actual results array

        if 'error' in result:
            raise RuntimeError(f"Turso SQL Error: {result['error']}")

        # Simplified result object for the application logic to consume
        return {
            "rows": result.get('rows', []),
            "rows_affected": result.get('rows_affected', 0),
            "columns": result.get('cols', [])
        }
        
    except requests.exceptions.RequestException as e:
        print(f"HTTP Request Error to Turso: {e}")
        raise RuntimeError(f"Connection or request failed: {e}")
    except Exception as e:
        print(f"Database Execution Error: {e}")
        raise RuntimeError(f"SQL execution failed: {e}")

def initialize_db():
    """Ensures necessary tables are created and sets up default categories."""
    
    # We execute all initialization queries in one place for safety
    statements = [
        "CREATE TABLE IF NOT EXISTS categories (name TEXT PRIMARY KEY NOT NULL)",
        "CREATE TABLE IF NOT EXISTS expenses (id TEXT PRIMARY KEY NOT NULL, category TEXT NOT NULL, amount REAL NOT NULL, date TEXT NOT NULL, description TEXT)",
        "CREATE TABLE IF NOT EXISTS budget (category TEXT PRIMARY KEY NOT NULL, limit_amount REAL NOT NULL)"
    ]
    
    try:
        # Run DDL statements
        for q in statements:
            execute_sql(q)

        # Check if we need to insert defaults
        existing_cats_res = execute_sql("SELECT COUNT(*) FROM categories")
        # Extract count from the simplified result structure
        existing_cats = existing_cats_res['rows'][0][0] if existing_cats_res['rows'] else 0
        
        # Insert default categories if none exist (Only on first run)
        if existing_cats == 0:
            default_categories = ["Food", "Travel", "Entertainment"]
            for cat in default_categories:
                execute_sql(f"INSERT INTO categories (name) VALUES ('{cat}')")
                execute_sql(f"INSERT INTO budget (category, limit_amount) VALUES ('{cat}', 0.0)")

    except Exception as e:
        # Log the error but continue if possible (Vercel might be strict)
        print(f"Database Initialization Warning: {e}")


def load_app_data():
    """Loads all application state from the database into a dictionary."""
    
    # Load Categories
    categories_res = execute_sql("SELECT name FROM categories ORDER BY name ASC")
    categories = [row[0] for row in categories_res['rows']]
    
    # Load Budget
    budget_res = execute_sql("SELECT category, limit_amount FROM budget")
    budget = {row[0]: row[1] for row in budget_res['rows']}
    
    # Load Expenses (Ordered by date, newest first)
    expenses_res = execute_sql("SELECT id, category, amount, date, description FROM expenses ORDER BY date DESC")
    expenses = [
        {"id": row[0], "category": row[1], "amount": row[2], "date": row[3], "description": row[4]} 
        for row in expenses_res['rows']
    ]
    
    return {
        "budget": budget,
        "expenses": expenses,
        "categories": categories
    }

# 3. Initialize DB and Load Data on Application Start
initialize_db()
app_data = load_app_data() # Load global application state from Turso

# --- API Endpoints ---

@app.route('/')
def index():
    """Renders the main single-page application template (requires index.html)."""
    return render_template('index.html')

@app.route('/api/state', methods=['GET'])
def get_state():
    """Returns the current application state from the database."""
    global app_data
    # Re-fetch state from DB to ensure latest data is returned
    app_data = load_app_data() 
    return jsonify(app_data)

@app.route('/api/categories', methods=['POST'])
def handle_categories():
    """Adds or removes a category, persisting changes to Turso."""
    global app_data
    try:
        req_data = request.get_json()
        action = req_data.get('action')
        category_name = req_data.get('category').strip().title().replace("'", "''")

        if not category_name:
            return jsonify({"message": "Category name cannot be empty."}), 400

        app_data = load_app_data() # Reload state
        
        if action == 'add':
            if category_name in app_data['categories']:
                return jsonify({"message": f"Category '{category_name}' already exists."}), 409
            
            # --- PERSISTENCE: Insert new category into DB ---
            execute_sql(f"INSERT INTO categories (name) VALUES ('{category_name}')")
            execute_sql(f"INSERT INTO budget (category, limit_amount) VALUES ('{category_name}', 0.0)")
            
            app_data = load_app_data() # Refresh global state
            return jsonify({"message": f"Category '{category_name}' added.", "data": app_data})
        
        elif action == 'remove':
            if category_name not in app_data['categories']:
                return jsonify({"message": f"Category '{category_name}' not found."}), 404
            
            # --- PERSISTENCE: Delete from DB tables ---
            execute_sql(f"DELETE FROM categories WHERE name = '{category_name}'")
            execute_sql(f"DELETE FROM budget WHERE category = '{category_name}'")
            execute_sql(f"DELETE FROM expenses WHERE category = '{category_name}'")

            app_data = load_app_data() # Refresh global state
            return jsonify({"message": f"Category '{category_name}' removed.", "data": app_data})

        return jsonify({"message": "Invalid category action."}), 400

    except Exception as e:
        print(f"Category Error: {e}")
        return jsonify({"message": f"An error occurred: {str(e)}"}), 500

@app.route('/api/budget', methods=['POST'])
def set_budget():
    """Sets the monthly budget for categories, persisting changes to Turso."""
    global app_data
    try:
        new_budget = request.get_json()
        
        app_data = load_app_data() # Reload state
        validated_budget = {}
        
        for cat in app_data['categories']:
            amount = new_budget.get(cat)
            if amount is not None:
                try:
                    amount = float(amount)
                    validated_budget[cat] = amount
                except ValueError:
                    return jsonify({"message": f"Invalid amount provided for category '{cat}'."}), 400
            else:
                validated_budget[cat] = app_data['budget'].get(cat, 0.0)

        # --- PERSISTENCE: Update/Insert all budgets into DB ---
        for cat, amount in validated_budget.items():
            execute_sql(f"REPLACE INTO budget (category, limit_amount) VALUES ('{cat}', {amount})")

        app_data = load_app_data() # Refresh global state
        return jsonify({"message": "Budget updated successfully!", "data": app_data})

    except Exception as e:
        print(f"Budget Error: {e}")
        return jsonify({"message": f"An error occurred: {str(e)}"}), 500

@app.route('/api/expense', methods=['POST'])
def add_expense():
    """Adds a new expense transaction, persisting to Turso."""
    global app_data
    try:
        req_data = request.get_json()
        category = req_data.get('category').strip().title()
        amount_str = req_data.get('amount')
        description = req_data.get('description', '').strip().replace("'", "''") # Basic SQL escaping
        expense_id = str(uuid.uuid4())

        app_data = load_app_data() # Reload state
        
        if category not in app_data['categories']:
            return jsonify({"message": f"Category '{category}' is not a recognized budget category."}), 400
        
        try:
            amount = float(amount_str)
            if amount <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return jsonify({"message": "Please enter a valid positive amount."}), 400

        date = datetime.now().strftime("%Y-%m-%d")
        
        # --- PERSISTENCE: Insert new expense into DB ---
        execute_sql(f"""
            INSERT INTO expenses (id, category, amount, date, description)
            VALUES ('{expense_id}', '{category}', {amount}, '{date}', '{description}')
        """)

        app_data = load_app_data() # Refresh global state
        return jsonify({"message": "Expense added successfully!", "data": app_data['expenses'][0]}) # Return the newest expense

    except Exception as e:
        print(f"Expense Error: {e}")
        return jsonify({"message": f"An error occurred: {str(e)}"}), 500

@app.route('/api/expense/<expense_id>', methods=['DELETE'])
def delete_expense_api(expense_id):
    """Deletes an expense transaction by ID, persisting change to Turso."""
    global app_data
    
    # --- PERSISTENCE: Delete from DB ---
    result = execute_sql(f"DELETE FROM expenses WHERE id = '{expense_id}'")

    if result.get('rows_affected', 0) == 0:
        return jsonify({"message": f"Expense with ID {expense_id} not found."}), 404

    app_data = load_app_data() # Refresh global state
    return jsonify({"message": "Expense successfully removed!"}), 200


@app.route('/api/report', methods=['GET'])
def generate_report():
    """Calculates and returns the full expense report."""
    
    global app_data
    app_data = load_app_data() # Always reload data for the report

    current_budget = app_data.get('budget', {})
    current_expenses = app_data.get('expenses', [])
    categories = app_data.get('categories', [])

    # 1. Calculate spent by category
    spent_by_category = {}
    total_spent = 0.0
    for entry in current_expenses:
        cat = entry.get("category")
        amt = entry.get("amount", 0.0)
        
        if cat in categories:
            spent_by_category[cat] = spent_by_category.get(cat, 0) + amt
            total_spent += amt

    # 2. Compile the report data
    report = []
    total_budget = 0.0
    for cat in categories:
        spent = spent_by_category.get(cat, 0.0)
        limit = current_budget.get(cat, 0.0)
        diff = spent - limit
        
        total_budget += limit

        report.append({
            "category": cat,
            "spent": spent,
            "budget": limit,
            "difference": diff,
            "status": "Within Budget" if diff <= 0 else "Over Budget"
        })
        
    return jsonify({
        "report": report, 
        "total_spent": total_spent, 
        "total_budget": total_budget,
        "expenses_log": current_expenses 
    })


if __name__ == '__main__':
    # Standard Flask run, initialization is handled above the routes
    app.run(debug=True)