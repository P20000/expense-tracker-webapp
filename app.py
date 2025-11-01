import json
import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for

# --- Configuration and Data Persistence ---
DATA_FILE = 'data.json'
app = Flask(__name__)
app.secret_key = 'super_secret_key' # For session management, though not used here

def load_data():
    """Loads application state (budget, expenses, categories) from DATA_FILE."""
    if os.path.exists(DATA_FILE) and os.path.getsize(DATA_FILE) > 0:
        with open(DATA_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                # Handle corrupted JSON file
                print(f"Warning: {DATA_FILE} is corrupted. Starting with default data.")
                return initialize_data()
    return initialize_data()

def initialize_data():
    """Sets up the initial state."""
    return {
        "budget": {},
        "expenses": [],
        "categories": ["Food", "Travel", "Entertainment"]
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
            app_data['categories'].append(category_name)
            app_data['budget'][category_name] = 0.0 # Initialize new category budget to zero
            save_data(app_data)
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
                # If a category is missing, assume 0.0 or keep existing if not explicitly setting all
                # For simplicity, we assume the frontend sends all current categories.
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
        "expenses_log": current_expenses
    })


if __name__ == '__main__':
    # Ensure the data file exists on first run
    if not os.path.exists(DATA_FILE):
        save_data(initialize_data())
    
    app.run(debug=True)
