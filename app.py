import os
import uuid
import json
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for
from turso import Client, ResultSet # Import the Turso client

# --- Configuration and Database Initialization ---

app = Flask(__name__)

# 1. Load Secure Environment Variables
DATABASE_URL = os.environ.get('DATABASE_URL') 
DATABASE_AUTH_TOKEN = os.environ.get('DATABASE_AUTH_TOKEN')
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24).hex()) 

# Check for required credentials (Crucial for Vercel deployment)
if not DATABASE_URL or not DATABASE_AUTH_TOKEN:
    # This will cause a clean crash on startup if variables are missing
    raise ValueError("FATAL: Database URL or Auth Token not set in Vercel Environment Variables.")

# 2. Database Client Setup (Global access to the client)
try:
    TURSO_CLIENT = Client(url=DATABASE_URL, auth_token=DATABASE_AUTH_TOKEN)
except Exception as e:
    raise RuntimeError(f"Failed to initialize Turso client: {e}")

def execute_sql(sql_query, params=None):
    """A helper function to safely execute SQL queries against Turso."""
    try:
        if params is None:
            return TURSO_CLIENT.execute(sql_query)
        else:
            return TURSO_CLIENT.execute(sql_query, params)
    except Exception as e:
        print(f"Database Error: {e}")
        # Re-raise the error to be caught by the Flask route handler or startup process
        raise RuntimeError(f"SQL execution failed: {e}")

def initialize_db():
    """Ensures necessary tables are created and sets up default categories."""
    
    # Create Categories Table
    execute_sql("""
        CREATE TABLE IF NOT EXISTS categories (
            name TEXT PRIMARY KEY NOT NULL
        )
    """)
    # Create Expenses Table
    execute_sql("""
        CREATE TABLE IF NOT EXISTS expenses (
            id TEXT PRIMARY KEY NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            date TEXT NOT NULL,
            description TEXT
        )
    """)
    # Create Budget Table (Category and its budget limit)
    execute_sql("""
        CREATE TABLE IF NOT EXISTS budget (
            category TEXT PRIMARY KEY NOT NULL,
            limit_amount REAL NOT NULL
        )
    """)

    # Insert default categories if none exist (Only on first run)
    default_categories = ["Food", "Travel", "Entertainment"]
    
    # Check if we need to insert defaults
    existing_cats = execute_sql("SELECT COUNT(*) FROM categories").rows[0][0]
    if existing_cats == 0:
        for cat in default_categories:
            execute_sql("INSERT INTO categories (name) VALUES (?)", [cat])
            execute_sql("INSERT INTO budget (category, limit_amount) VALUES (?, 0.0)", [cat])

def load_app_data():
    """Loads all application state from the database into a dictionary."""
    
    # Load Categories
    categories_res = execute_sql("SELECT name FROM categories ORDER BY name ASC")
    categories = [row[0] for row in categories_res.rows]
    
    # Load Budget
    budget_res = execute_sql("SELECT category, limit_amount FROM budget")
    budget = {row[0]: row[1] for row in budget_res.rows}
    
    # Load Expenses (Ordered by date, newest first)
    expenses_res = execute_sql("SELECT id, category, amount, date, description FROM expenses ORDER BY date DESC")
    expenses = [
        {"id": row[0], "category": row[1], "amount": row[2], "date": row[3], "description": row[4]} 
        for row in expenses_res.rows
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
    """Returns the current application state from the in-memory global data."""
    global app_data
    # Re-fetch just in case data was modified in another thread (good practice)
    app_data = load_app_data() 
    return jsonify(app_data)

@app.route('/api/categories', methods=['POST'])
def handle_categories():
    """Adds or removes a category, persisting changes to Turso."""
    global app_data
    try:
        req_data = request.get_json()
        action = req_data.get('action')
        category_name = req_data.get('category').strip().title()

        if not category_name:
            return jsonify({"message": "Category name cannot be empty."}), 400

        if action == 'add':
            if category_name in app_data['categories']:
                return jsonify({"message": f"Category '{category_name}' already exists."}), 409
            
            # --- PERSISTENCE: Insert new category into DB ---
            execute_sql("INSERT INTO categories (name) VALUES (?)", [category_name])
            execute_sql("INSERT INTO budget (category, limit_amount) VALUES (?, 0.0)", [category_name])
            
            # Refresh global state
            app_data = load_app_data()
            return jsonify({"message": f"Category '{category_name}' added.", "data": app_data})
        
        elif action == 'remove':
            if category_name not in app_data['categories']:
                return jsonify({"message": f"Category '{category_name}' not found."}), 404
            
            # --- PERSISTENCE: Delete from DB tables ---
            execute_sql("DELETE FROM categories WHERE name = ?", [category_name])
            execute_sql("DELETE FROM budget WHERE category = ?", [category_name])
            execute_sql("DELETE FROM expenses WHERE category = ?", [category_name]) # Clean up associated expenses

            # Refresh global state
            app_data = load_app_data()
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
        
        # Validate and prepare budget update
        validated_budget = {}
        for cat in app_data['categories']:
            amount = new_budget.get(cat)
            if amount is not None:
                try:
                    validated_budget[cat] = float(amount)
                except ValueError:
                    return jsonify({"message": f"Invalid amount provided for category '{cat}'."}), 400
            else:
                # If amount is not explicitly provided, keep the old value
                validated_budget[cat] = app_data['budget'].get(cat, 0.0)

        # --- PERSISTENCE: Update/Insert all budgets into DB ---
        for cat, amount in validated_budget.items():
            # REPLACE INTO updates if key exists, inserts if key does not exist
            execute_sql("REPLACE INTO budget (category, limit_amount) VALUES (?, ?)", [cat, amount])

        # Refresh global state
        app_data = load_app_data()
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
        description = req_data.get('description', '').strip()
        expense_id = str(uuid.uuid4())

        if category not in app_data['categories']:
            return jsonify({"message": f"Category '{category}' is not a recognized budget category."}), 400
        
        try:
            amount = float(amount_str)
            if amount <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return jsonify({"message": "Please enter a valid positive amount."}), 400

        date = datetime.now().strftime("%Y-%m-%d")
        
        new_expense = {
            "id": expense_id,
            "category": category,
            "amount": amount,
            "date": date,
            "description": description
        }

        # --- PERSISTENCE: Insert new expense into DB ---
        execute_sql("""
            INSERT INTO expenses (id, category, amount, date, description)
            VALUES (?, ?, ?, ?, ?)
        """, [
            new_expense['id'], 
            new_expense['category'], 
            new_expense['amount'], 
            new_expense['date'], 
            new_expense['description']
        ])

        # Refresh global state
        app_data = load_app_data()
        return jsonify({"message": "Expense added successfully!", "data": new_expense})

    except Exception as e:
        print(f"Expense Error: {e}")
        return jsonify({"message": f"An error occurred: {str(e)}"}), 500

@app.route('/api/expense/<expense_id>', methods=['DELETE'])
def delete_expense_api(expense_id):
    """Deletes an expense transaction by ID, persisting change to Turso."""
    global app_data
    
    # --- PERSISTENCE: Delete from DB ---
    result = execute_sql("DELETE FROM expenses WHERE id = ?", [expense_id])

    # Check rows_affected to see if a deletion occurred
    if result.rows_affected == 0:
        return jsonify({"message": f"Expense with ID {expense_id} not found."}), 404

    # Refresh global state
    app_data = load_app_data()
    return jsonify({"message": "Expense successfully removed!"}), 200


@app.route('/api/report', methods=['GET'])
def generate_report():
    """Calculates and returns the full expense report."""
    
    # Reload data to ensure report is based on the latest DB state
    global app_data
    app_data = load_app_data()

    current_budget = app_data.get('budget', {})
    current_expenses = app_data.get('expenses', [])
    categories = app_data.get('categories', [])

    # 1. Calculate spent by category
    spent_by_category = {}
    total_spent = 0.0
    for entry in current_expenses:
        cat = entry.get("category")
        amt = entry.get("amount", 0.0)
        
        # Only count if the category is still active/budgeted
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
