import os
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from config import Config
from models import db, Category, Medicine, Batch, StockTransaction
from services.inventory_logic import (
    calculate_safety_stock,
    calculate_min_stock,
    calculate_max_stock,
    get_inventory_status,
    get_expiry_status,
    sort_fefo_batches
)


def create_app(config_class=Config):
    """Application factory for PharmaStock."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)

    # Register custom template filters
    @app.template_filter('currency')
    def currency_filter(value):
        try:
            return f"${float(value):,.2f}"
        except (ValueError, TypeError):
            return "$0.00"

    @app.template_filter('format_date')
    def format_date_filter(val):
        if not val:
            return "N/A"
        if isinstance(val, (datetime, date)):
            return val.strftime("%d %b %Y")
        return str(val)

    # -------------------------------------------------------------
    # 1. Dashboard Route
    # -------------------------------------------------------------
    @app.route('/')
    def dashboard():
        medicines = Medicine.query.all()
        batches = Batch.query.all()
        today = date.today()

        # Compute key inventory metrics
        total_medicines = len(medicines)
        
        # Low stock medicines (current usable stock <= min stock)
        low_stock_medicines = [m for m in medicines if m.stock_status in ('LOW_STOCK', 'CRITICAL_LOW', 'OUT_OF_STOCK')]
        
        # Expired and expiring batches
        expired_batches = [b for b in batches if b.expiry_date <= today and b.quantity > 0]
        critical_expiry_batches = [
            b for b in batches 
            if today < b.expiry_date <= today + timedelta(days=30) and b.quantity > 0
        ]
        warning_expiry_batches = [
            b for b in batches 
            if today + timedelta(days=30) < b.expiry_date <= today + timedelta(days=90) and b.quantity > 0
        ]

        # Total inventory financial value (cost of non-expired goods)
        total_valuation = sum(
            (b.quantity * b.purchase_price) 
            for b in batches 
            if b.expiry_date > today and b.quantity > 0
        )

        # Recent transactions (last 6)
        recent_transactions = (
            StockTransaction.query.order_by(StockTransaction.timestamp.desc()).limit(6).all()
        )

        # Action needed alerts (top urgent items)
        critical_alerts = []
        for b in expired_batches:
            critical_alerts.append({
                'type': 'danger',
                'badge': 'EXPIRED',
                'title': f"{b.medicine.brand_name} (Batch {b.batch_number})",
                'message': f"Expired on {b.expiry_date.strftime('%d %b %Y')} ({abs(b.days_until_expiry)} days ago). Quarantine {b.quantity} {b.medicine.unit} immediately.",
                'medicine_id': b.medicine.id
            })

        for b in critical_expiry_batches:
            critical_alerts.append({
                'type': 'warning',
                'badge': 'CRITICAL EXPIRY',
                'title': f"{b.medicine.brand_name} (Batch {b.batch_number})",
                'message': f"Expires in {b.days_until_expiry} days ({b.expiry_date.strftime('%d %b %Y')}). {b.quantity} {b.medicine.unit} remaining.",
                'medicine_id': b.medicine.id
            })

        for m in low_stock_medicines:
            critical_alerts.append({
                'type': 'info',
                'badge': 'REORDER NEEDED',
                'title': f"{m.brand_name} ({m.generic_name})",
                'message': f"Stock is {m.total_stock} {m.unit} (Min Reorder Point is {m.min_stock} {m.unit}).",
                'medicine_id': m.id
            })

        return render_template(
            'dashboard.html',
            total_medicines=total_medicines,
            low_stock_count=len(low_stock_medicines),
            expired_count=len(expired_batches),
            critical_expiry_count=len(critical_expiry_batches),
            warning_expiry_count=len(warning_expiry_batches),
            total_valuation=total_valuation,
            recent_transactions=recent_transactions,
            critical_alerts=critical_alerts[:5],
            medicines=medicines
        )

    # -------------------------------------------------------------
    # 2. Inventory Listing & Search
    # -------------------------------------------------------------
    @app.route('/inventory')
    def inventory():
        query = Medicine.query
        search = request.args.get('search', '').strip()
        status_filter = request.args.get('status', 'all')
        category_id = request.args.get('category', type=int)

        if search:
            query = query.filter(
                (Medicine.brand_name.ilike(f"%{search}%")) |
                (Medicine.generic_name.ilike(f"%{search}%")) |
                (Medicine.strength.ilike(f"%{search}%"))
            )

        if category_id:
            query = query.filter(Medicine.category_id == category_id)

        medicines = query.order_by(Medicine.brand_name.asc()).all()

        # In-memory status filtering based on dynamic pharmacy rules
        if status_filter == 'low_stock':
            medicines = [m for m in medicines if m.stock_status in ('LOW_STOCK', 'CRITICAL_LOW', 'OUT_OF_STOCK')]
        elif status_filter == 'expiring_soon':
            medicines = [
                m for m in medicines 
                if any(0 < b.days_until_expiry <= 90 and b.quantity > 0 for b in m.batches)
            ]
        elif status_filter == 'expired':
            medicines = [
                m for m in medicines 
                if any(b.days_until_expiry <= 0 and b.quantity > 0 for b in m.batches)
            ]
        elif status_filter == 'overstocked':
            medicines = [m for m in medicines if m.stock_status == 'OVERSTOCKED']

        categories = Category.query.order_by(Category.name.asc()).all()

        return render_template(
            'inventory.html',
            medicines=medicines,
            categories=categories,
            search=search,
            current_status=status_filter,
            current_category=category_id
        )

    # -------------------------------------------------------------
    # 3. Medicine Management (CRUD)
    # -------------------------------------------------------------
    @app.route('/medicine/add', methods=['GET', 'POST'])
    def add_medicine():
        categories = Category.query.order_by(Category.name.asc()).all()

        if request.method == 'POST':
            brand_name = request.form.get('brand_name', '').strip()
            generic_name = request.form.get('generic_name', '').strip()
            category_id = request.form.get('category_id', type=int)
            dosage_form = request.form.get('dosage_form', 'Tablet').strip()
            strength = request.form.get('strength', '').strip()
            unit = request.form.get('unit', 'Tablets').strip()

            avg_daily_consumption = float(request.form.get('avg_daily_consumption', 10.0))
            lead_time_days = int(request.form.get('lead_time_days', 7))
            safety_stock_days = int(request.form.get('safety_stock_days', 5))

            if not brand_name or not generic_name or not category_id:
                flash("Please fill in all required fields (Brand Name, Generic Name, Category).", "danger")
                return render_template('medicine_form.html', categories=categories, medicine=None)

            new_med = Medicine(
                brand_name=brand_name,
                generic_name=generic_name,
                category_id=category_id,
                dosage_form=dosage_form,
                strength=strength,
                unit=unit,
                avg_daily_consumption=avg_daily_consumption,
                lead_time_days=lead_time_days,
                safety_stock_days=safety_stock_days
            )
            db.session.add(new_med)
            db.session.flush()

            # Optional initial batch creation
            batch_number = request.form.get('batch_number', '').strip()
            batch_qty = request.form.get('initial_quantity', type=int)
            expiry_str = request.form.get('expiry_date')

            if batch_number and batch_qty and batch_qty > 0 and expiry_str:
                expiry_date = datetime.strptime(expiry_str, '%Y-%m-%d').date()
                purchase_price = float(request.form.get('purchase_price', 0.0) or 0.0)
                selling_price = float(request.form.get('selling_price', 0.0) or 0.0)
                supplier = request.form.get('supplier', '').strip()

                batch = Batch(
                    medicine_id=new_med.id,
                    batch_number=batch_number,
                    quantity=batch_qty,
                    initial_quantity=batch_qty,
                    expiry_date=expiry_date,
                    purchase_price=purchase_price,
                    selling_price=selling_price,
                    supplier=supplier
                )
                db.session.add(batch)
                db.session.flush()

                # Record stock intake transaction
                trans = StockTransaction(
                    medicine_id=new_med.id,
                    batch_id=batch.id,
                    transaction_type="RESTOCK",
                    quantity=batch_qty,
                    reference_no="INIT-STOCK",
                    notes="Initial batch recorded during medicine creation"
                )
                db.session.add(trans)

            db.session.commit()
            flash(f"Medicine '{brand_name}' created successfully!", "success")
            return redirect(url_for('medicine_detail', id=new_med.id))

        return render_template('medicine_form.html', categories=categories, medicine=None)

    @app.route('/medicine/<int:id>')
    def medicine_detail(id):
        medicine = Medicine.query.get_or_404(id)
        # Sort batches in FEFO order
        sorted_batches = sorted(medicine.batches, key=lambda b: (b.expiry_date, -b.quantity))
        transactions = (
            StockTransaction.query.filter_by(medicine_id=id)
            .order_by(StockTransaction.timestamp.desc())
            .limit(20)
            .all()
        )
        return render_template(
            'medicine_detail.html',
            medicine=medicine,
            batches=sorted_batches,
            transactions=transactions
        )

    @app.route('/medicine/<int:id>/edit', methods=['GET', 'POST'])
    def edit_medicine(id):
        medicine = Medicine.query.get_or_404(id)
        categories = Category.query.order_by(Category.name.asc()).all()

        if request.method == 'POST':
            medicine.brand_name = request.form.get('brand_name', '').strip()
            medicine.generic_name = request.form.get('generic_name', '').strip()
            medicine.category_id = request.form.get('category_id', type=int)
            medicine.dosage_form = request.form.get('dosage_form', 'Tablet').strip()
            medicine.strength = request.form.get('strength', '').strip()
            medicine.unit = request.form.get('unit', 'Tablets').strip()

            medicine.avg_daily_consumption = float(request.form.get('avg_daily_consumption', 10.0))
            medicine.lead_time_days = int(request.form.get('lead_time_days', 7))
            medicine.safety_stock_days = int(request.form.get('safety_stock_days', 5))

            db.session.commit()
            flash(f"Updated parameters for '{medicine.brand_name}'.", "success")
            return redirect(url_for('medicine_detail', id=medicine.id))

        return render_template('medicine_form.html', categories=categories, medicine=medicine)

    @app.route('/medicine/<int:id>/delete', methods=['POST'])
    def delete_medicine(id):
        medicine = Medicine.query.get_or_404(id)
        name = medicine.brand_name
        db.session.delete(medicine)
        db.session.commit()
        flash(f"Medicine '{name}' and all associated batches removed.", "info")
        return redirect(url_for('inventory'))

    # -------------------------------------------------------------
    # 4. Batch Operations (Add, Edit, FEFO Management)
    # -------------------------------------------------------------
    @app.route('/batch/add/<int:medicine_id>', methods=['GET', 'POST'])
    def add_batch(medicine_id):
        medicine = Medicine.query.get_or_404(medicine_id)

        if request.method == 'POST':
            batch_number = request.form.get('batch_number', '').strip()
            quantity = request.form.get('quantity', type=int)
            expiry_str = request.form.get('expiry_date')
            purchase_price = float(request.form.get('purchase_price', 0.0) or 0.0)
            selling_price = float(request.form.get('selling_price', 0.0) or 0.0)
            supplier = request.form.get('supplier', '').strip()
            ref_no = request.form.get('reference_no', '').strip() or "PURCHASE-IN"

            if not batch_number or not quantity or quantity <= 0 or not expiry_str:
                flash("Batch number, valid positive quantity, and expiry date are required.", "danger")
                return render_template('batch_form.html', medicine=medicine, batch=None)

            expiry_date = datetime.strptime(expiry_str, '%Y-%m-%d').date()

            new_batch = Batch(
                medicine_id=medicine.id,
                batch_number=batch_number,
                quantity=quantity,
                initial_quantity=quantity,
                expiry_date=expiry_date,
                purchase_price=purchase_price,
                selling_price=selling_price,
                supplier=supplier
            )
            db.session.add(new_batch)
            db.session.flush()

            # Record RESTOCK transaction
            trans = StockTransaction(
                medicine_id=medicine.id,
                batch_id=new_batch.id,
                transaction_type="RESTOCK",
                quantity=quantity,
                reference_no=ref_no,
                notes=f"New batch received from {supplier or 'Supplier'}"
            )
            db.session.add(trans)
            db.session.commit()

            flash(f"Batch {batch_number} for {medicine.brand_name} added to inventory.", "success")
            return redirect(url_for('medicine_detail', id=medicine.id))

        return render_template('batch_form.html', medicine=medicine, batch=None)

    @app.route('/batch/<int:id>/edit', methods=['GET', 'POST'])
    def edit_batch(id):
        batch = Batch.query.get_or_404(id)
        medicine = batch.medicine

        if request.method == 'POST':
            batch.batch_number = request.form.get('batch_number', '').strip()
            old_qty = batch.quantity
            new_qty = request.form.get('quantity', type=int)
            expiry_str = request.form.get('expiry_date')
            batch.purchase_price = float(request.form.get('purchase_price', 0.0) or 0.0)
            batch.selling_price = float(request.form.get('selling_price', 0.0) or 0.0)
            batch.supplier = request.form.get('supplier', '').strip()

            if expiry_str:
                batch.expiry_date = datetime.strptime(expiry_str, '%Y-%m-%d').date()

            if new_qty is not None and new_qty != old_qty:
                diff = new_qty - old_qty
                batch.quantity = new_qty
                # Log manual audit adjustment
                trans = StockTransaction(
                    medicine_id=medicine.id,
                    batch_id=batch.id,
                    transaction_type="ADJUSTMENT",
                    quantity=abs(diff),
                    reference_no="AUDIT-ADJ",
                    notes=f"Stock count manually adjusted from {old_qty} to {new_qty}"
                )
                db.session.add(trans)

            db.session.commit()
            flash(f"Batch {batch.batch_number} updated successfully.", "success")
            return redirect(url_for('medicine_detail', id=medicine.id))

        return render_template('batch_form.html', medicine=medicine, batch=batch)

    # -------------------------------------------------------------
    # 5. Dispensing (Stock Out) with FEFO Priority
    # -------------------------------------------------------------
    @app.route('/dispense', methods=['GET', 'POST'])
    def dispense():
        medicines = Medicine.query.order_by(Medicine.brand_name.asc()).all()
        preselected_med_id = request.args.get('medicine_id', type=int)

        if request.method == 'POST':
            med_id = request.form.get('medicine_id', type=int)
            batch_id = request.form.get('batch_id', type=int)
            quantity = request.form.get('quantity', type=int)
            ref_no = request.form.get('reference_no', '').strip() or "RX-DISPENSE"
            notes = request.form.get('notes', '').strip()

            if not med_id or not quantity or quantity <= 0:
                flash("Please select a valid medicine and enter a dispensing quantity > 0.", "danger")
                return redirect(url_for('dispense', medicine_id=med_id))

            medicine = Medicine.query.get_or_404(med_id)

            # Determine batch to dispense from (FEFO priority)
            if batch_id:
                batch = Batch.query.get_or_404(batch_id)
            else:
                batch = medicine.earliest_expiring_batch

            if not batch:
                flash(f"No active batches with stock available for {medicine.brand_name}.", "danger")
                return redirect(url_for('dispense', medicine_id=med_id))

            # Validate stock sufficiency
            if quantity > batch.quantity:
                flash(
                    f"Insufficient stock in Batch {batch.batch_number}! Requested: {quantity}, Available: {batch.quantity}.",
                    "danger"
                )
                return redirect(url_for('dispense', medicine_id=med_id))

            # Deduct stock
            batch.quantity -= quantity

            # Record audit transaction
            trans = StockTransaction(
                medicine_id=medicine.id,
                batch_id=batch.id,
                transaction_type="DISPENSE",
                quantity=quantity,
                reference_no=ref_no,
                notes=notes or f"Dispensed under FEFO from Batch {batch.batch_number}"
            )
            db.session.add(trans)
            db.session.commit()

            flash(f"Successfully dispensed {quantity} {medicine.unit} of {medicine.brand_name} (Batch: {batch.batch_number}).", "success")
            return redirect(url_for('medicine_detail', id=medicine.id))

        return render_template(
            'dispense.html',
            medicines=medicines,
            preselected_med_id=preselected_med_id
        )

    # -------------------------------------------------------------
    # 6. Restock (Stock In)
    # -------------------------------------------------------------
    @app.route('/restock', methods=['GET', 'POST'])
    def restock():
        medicines = Medicine.query.order_by(Medicine.brand_name.asc()).all()
        preselected_med_id = request.args.get('medicine_id', type=int)

        if request.method == 'POST':
            med_id = request.form.get('medicine_id', type=int)
            medicine = Medicine.query.get_or_404(med_id)

            batch_mode = request.form.get('batch_mode', 'new')
            quantity = request.form.get('quantity', type=int)
            ref_no = request.form.get('reference_no', '').strip() or "DELIVERY-IN"
            notes = request.form.get('notes', '').strip()

            if not quantity or quantity <= 0:
                flash("Please enter a valid received quantity greater than 0.", "danger")
                return redirect(url_for('restock', medicine_id=med_id))

            if batch_mode == 'existing':
                batch_id = request.form.get('existing_batch_id', type=int)
                batch = Batch.query.get_or_404(batch_id)
                batch.quantity += quantity
            else:
                batch_number = request.form.get('batch_number', '').strip()
                expiry_str = request.form.get('expiry_date')
                purchase_price = float(request.form.get('purchase_price', 0.0) or 0.0)
                selling_price = float(request.form.get('selling_price', 0.0) or 0.0)
                supplier = request.form.get('supplier', '').strip()

                if not batch_number or not expiry_str:
                    flash("Batch Number and Expiry Date are required when receiving a new batch.", "danger")
                    return redirect(url_for('restock', medicine_id=med_id))

                expiry_date = datetime.strptime(expiry_str, '%Y-%m-%d').date()

                batch = Batch(
                    medicine_id=medicine.id,
                    batch_number=batch_number,
                    quantity=quantity,
                    initial_quantity=quantity,
                    expiry_date=expiry_date,
                    purchase_price=purchase_price,
                    selling_price=selling_price,
                    supplier=supplier
                )
                db.session.add(batch)
                db.session.flush()

            # Record transaction
            trans = StockTransaction(
                medicine_id=medicine.id,
                batch_id=batch.id,
                transaction_type="RESTOCK",
                quantity=quantity,
                reference_no=ref_no,
                notes=notes or f"Restock delivery received (Batch: {batch.batch_number})"
            )
            db.session.add(trans)
            db.session.commit()

            flash(f"Received {quantity} {medicine.unit} into {medicine.brand_name} stock.", "success")
            return redirect(url_for('medicine_detail', id=medicine.id))

        return render_template(
            'restock.html',
            medicines=medicines,
            preselected_med_id=preselected_med_id
        )

    # -------------------------------------------------------------
    # 7. Audit Log / Transaction History
    # -------------------------------------------------------------
    @app.route('/transactions')
    def transactions():
        tx_type = request.args.get('type')
        query = StockTransaction.query

        if tx_type:
            query = query.filter_by(transaction_type=tx_type)

        tx_list = query.order_by(StockTransaction.timestamp.desc()).all()
        return render_template('transactions.html', transactions=tx_list, current_type=tx_type)

    # -------------------------------------------------------------
    # 8. Categories View
    # -------------------------------------------------------------
    @app.route('/categories', methods=['GET', 'POST'])
    def categories():
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            desc = request.form.get('description', '').strip()
            if name:
                existing = Category.query.filter_by(name=name).first()
                if not existing:
                    cat = Category(name=name, description=desc)
                    db.session.add(cat)
                    db.session.commit()
                    flash(f"Category '{name}' added successfully.", "success")
                else:
                    flash(f"Category '{name}' already exists.", "warning")
            return redirect(url_for('categories'))

        all_cats = Category.query.order_by(Category.name.asc()).all()
        return render_template('categories.html', categories=all_cats)

    # -------------------------------------------------------------
    # 9. API Helper (for dynamic FEFO suggestions in forms)
    # -------------------------------------------------------------
    @app.route('/api/medicine/<int:id>/batches')
    def api_medicine_batches(id):
        medicine = Medicine.query.get_or_404(id)
        # Sort FEFO
        active_batches = [b for b in medicine.batches if b.quantity > 0]
        sorted_batches = sorted(active_batches, key=lambda b: b.expiry_date)
        return jsonify([
            {
                'id': b.id,
                'batch_number': b.batch_number,
                'quantity': b.quantity,
                'expiry_date': b.expiry_date.strftime('%Y-%m-%d'),
                'days_until_expiry': b.days_until_expiry,
                'expiry_status': b.expiry_status,
                'is_fefo_priority': (b.id == sorted_batches[0].id) if sorted_batches else False
            }
            for b in sorted_batches
        ])

    return app


# Create default instance for running directly
app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)
