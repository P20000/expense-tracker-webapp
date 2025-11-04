import json
import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for
import uuid
from turso import Client, ResultSet # Import the Turso client

# --- Configuration and Data Persistence ---
DATA_FILE = 'data.json'
app = Flask(__name__)
DATABASE_URL = os.environ.get('DATABASE_URL') 
DATABASE_AUTH_TOKEN = os.environ.get('DATABASE_AUTH_TOKEN')
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24).hex()) 

# Check for required credentials (Crucial for Vercel deployment)
if not DATABASE_URL or not DATABASE_AUTH_TOKEN:
    # This will cause a clean crash on startup if variables are missing
    raise ValueError("FATAL: Database URL or Auth Token not set in Environment Variables.")

# 2. Database Client Setup (Global access is necessary for a simple app)
try:
    TURSO_CLIENT = Client(url=DATABASE_URL, auth_token=DATABASE_AUTH_TOKEN)
except Exception as e:
    raise RuntimeError(f"Failed to initialize Turso client: {e}")

def execute_sql(sql_query, params=None):
    """A helper function to safely execute SQL queries."""
    try:
        if params is None:
            return TURSO_CLIENT.execute(sql_query)
        else:
            return TURSO_CLIENT.execute(sql_query, params)
    except Exception as e:
        print(f"Database Error: {e}")
        # In a real app, you'd handle this better, but for deployment:
        raise RuntimeError(f"SQL execution failed: {e}")

def initialize_db():
    """Ensure tables exist and load initial structure."""
    
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
    
    # Check if we need to insert defaults (basic check)
    existing_cats = execute_sql("SELECT COUNT(*) FROM categories").rows[0][0]
    if existing_cats == 0:
        for cat in default_categories:
            execute_sql("INSERT INTO categories (name) VALUES (?)", [cat])
            execute_sql("INSERT INTO budget (category, limit_amount) VALUES (?, 0.0)", [cat])

# --- Rewritten Data Loading ---
def load_app_data():
    """Loads all application state from the database."""
    
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

def save_data(data):
    """Saves application state to DATA_FILE."""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# Load initial data on application start
app_data = load_data()

# --- API Endpoints ---

@app.route('/')
def index():
    """Renders the main single-page application template."""
    return render_template('index.html')

@app.route('/api/state', methods=['GET'])
def get_state():
    """Returns the current application state."""
    return jsonify(app_data)

@app.route('/api/categories', methods=['POST'])
def handle_categories():
    """Adds or removes a category."""
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
            # 1. Update DB tables (new category and initial budget)
            execute_sql("INSERT INTO categories (name) VALUES (?)", [category_name])
            execute_sql("INSERT INTO budget (category, limit_amount) VALUES (?, 0.0)", [category_name])
            
            # 2. Update the in-memory app_data object (Optional, but keeps state current)
            app_data['categories'].append(category_name)
            app_data['budget'][category_name] = 0.0 
            
            # Note: No separate save_data() call needed!
            return jsonify({"message": f"Category '{category_name}' added.", "data": app_data})
        
        elif action == 'remove':
            if category_name not in app_data['categories']:
                return jsonify({"message": f"Category '{category_name}' not found."}), 404
            
            # Remove from categories list
            app_data['categories'].remove(category_name)
            
            # Remove from budget map
            if category_name in app_data['budget']:
                del app_data['budget'][category_name]
            
            # Remove associated expenses (optional, but clean)
            app_data['expenses'] = [e for e in app_data['expenses'] if e['category'] != category_name]

            save_data(app_data)
            return jsonify({"message": f"Category '{category_name}' removed.", "data": app_data})

        return jsonify({"message": "Invalid category action."}), 400

    except Exception as e:
        print(f"Category Error: {e}")
        return jsonify({"message": f"An error occurred: {str(e)}"}), 500

@app.route('/api/budget', methods=['POST'])
def set_budget():
    """Sets the monthly budget for categories."""
    global app_data
    try:
        new_budget = request.get_json()
        
        # Validate that all keys are valid categories and values are numbers
        validated_budget = {}
        for cat in app_data['categories']:
            amount = new_budget.get(cat)
            if amount is not None:
                try:
                    validated_budget[cat] = float(amount)
                except ValueError:
                    return jsonify({"message": f"Invalid amount provided for category '{cat}'."}), 400
            else:
                validated_budget[cat] = app_data['budget'].get(cat, 0.0)

        app_data['budget'] = validated_budget
        save_data(app_data)
        return jsonify({"message": "Budget updated successfully!", "data": app_data})

    except Exception as e:
        print(f"Budget Error: {e}")
        return jsonify({"message": f"An error occurred: {str(e)}"}), 500

@app.route('/api/expense', methods=['POST'])
def add_expense():
    """Adds a new expense transaction."""
    global app_data
    try:
        req_data = request.get_json()
        category = req_data.get('category').strip().title()
        amount_str = req_data.get('amount')
        description = req_data.get('description', '').strip()

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
            "id": str(uuid.uuid4()), # NEW: Assign a unique ID to the expense
            "category": category,
            "amount": amount,
            "date": date,
            "description": description
        }

        app_data['expenses'].append(new_expense)
        save_data(app_data)
        return jsonify({"message": "Expense added successfully!", "data": new_expense})

    except Exception as e:
        print(f"Expense Error: {e}")
        return jsonify({"message": f"An error occurred: {str(e)}"}), 500

# NEW ENDPOINT: Handle DELETE requests for expenses by ID
@app.route('/api/expense/<expense_id>', methods=['DELETE'])
def delete_expense_api(expense_id):
    """Deletes an expense transaction by ID."""
    global app_data
    
    # Store the initial length to check if a deletion occurred
    original_length = len(app_data['expenses'])
    
    # Filter out the expense with the matching ID
    # Note: expense IDs are expected to be strings (UUIDs)
    app_data['expenses'] = [
        e for e in app_data['expenses'] 
        if e.get('id') != expense_id
    ]

    # Check if the list length changed
    if len(app_data['expenses']) == original_length:
        return jsonify({"message": f"Expense with ID {expense_id} not found."}), 404

    save_data(app_data)
    return jsonify({"message": "Expense successfully removed!"}), 200


@app.route('/api/report', methods=['GET'])
def generate_report():
    """Calculates and returns the full expense report."""
    
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
        "expenses_log": current_expenses # This now includes the unique 'id' field
    })


if __name__ == '__main__':
    # Ensure the data file exists on first run
    if not os.path.exists(DATA_FILE):
        save_data(initialize_data())
    
    app.run(debug=True)
