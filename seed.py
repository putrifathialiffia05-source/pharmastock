"""
PharmaStock Database Seeder
Populates the database with realistic pharmaceutical categories, medicines,
batches with various expiration horizons, and transaction logs.
"""

from datetime import date, datetime, timedelta
from app import create_app
from models import db, Category, Medicine, Batch, StockTransaction

def seed_database():
    app = create_app()
    with app.app_context():
        # Drop and recreate tables for a clean slate
        db.drop_all()
        db.create_all()

        print("Created database tables successfully.")

        # 1. Categories
        cat_analgesic = Category(name="Analgesics & Antipyretics", description="Pain relievers and fever reducers")
        cat_antibiotic = Category(name="Antibiotics", description="Antimicrobial medications for bacterial infections")
        cat_cardio = Category(name="Cardiovascular", description="Blood pressure and heart medications")
        cat_diabetes = Category(name="Antidiabetic", description="Oral hypoglycemic agents and insulin sensitizers")
        cat_gi = Category(name="Gastrointestinal", description="Antacids, PPIs, and digestive medications")
        cat_respiratory = Category(name="Respiratory", description="Bronchodilators, inhalers, and cough preparations")
        cat_allergy = Category(name="Antihistamines", description="Allergy and hypersensitivity relief")

        categories = [
            cat_analgesic, cat_antibiotic, cat_cardio,
            cat_diabetes, cat_gi, cat_respiratory, cat_allergy
        ]
        db.session.add_all(categories)
        db.session.flush()

        # 2. Medicines
        # Medicine 1: Paracetamol (Balanced, high turnover)
        med_paracetamol = Medicine(
            brand_name="Panadol Extra",
            generic_name="Paracetamol + Caffeine",
            category_id=cat_analgesic.id,
            dosage_form="Tablet",
            strength="500mg / 65mg",
            unit="Tablets",
            avg_daily_consumption=25.0,
            lead_time_days=5,
            safety_stock_days=4
        )

        # Medicine 2: Amoxicillin (Antibiotic with a critically expiring batch)
        med_amoxicillin = Medicine(
            brand_name="Amoxil",
            generic_name="Amoxicillin Trihydrate",
            category_id=cat_antibiotic.id,
            dosage_form="Capsule",
            strength="500mg",
            unit="Capsules",
            avg_daily_consumption=12.0,
            lead_time_days=7,
            safety_stock_days=5
        )

        # Medicine 3: Metformin (Chronic care drug currently LOW in stock)
        # Min stock = (20 * 10) + (20 * 7) = 340. We will set batches to total 120.
        med_metformin = Medicine(
            brand_name="Glucophage",
            generic_name="Metformin HCl",
            category_id=cat_diabetes.id,
            dosage_form="Tablet",
            strength="500mg",
            unit="Tablets",
            avg_daily_consumption=20.0,
            lead_time_days=10,
            safety_stock_days=7
        )

        # Medicine 4: Amlodipine (Has an EXPIRED batch for quarantine demo)
        med_amlodipine = Medicine(
            brand_name="Norvasc",
            generic_name="Amlodipine Besylate",
            category_id=cat_cardio.id,
            dosage_form="Tablet",
            strength="10mg",
            unit="Tablets",
            avg_daily_consumption=8.0,
            lead_time_days=7,
            safety_stock_days=5
        )

        # Medicine 5: Omeprazole (Healthy, normal inventory)
        med_omeprazole = Medicine(
            brand_name="Losec",
            generic_name="Omeprazole",
            category_id=cat_gi.id,
            dosage_form="Capsule",
            strength="20mg",
            unit="Capsules",
            avg_daily_consumption=10.0,
            lead_time_days=6,
            safety_stock_days=4
        )

        # Medicine 6: Salbutamol (Syrup with a batch expiring within 60 days)
        med_salbutamol = Medicine(
            brand_name="Ventolin",
            generic_name="Salbutamol Sulfate",
            category_id=cat_respiratory.id,
            dosage_form="Syrup",
            strength="2mg/5ml (100ml)",
            unit="Bottles",
            avg_daily_consumption=4.0,
            lead_time_days=8,
            safety_stock_days=5
        )

        # Medicine 7: Azithromycin (Antibiotic, good status)
        med_azithromycin = Medicine(
            brand_name="Zithromax",
            generic_name="Azithromycin",
            category_id=cat_antibiotic.id,
            dosage_form="Tablet",
            strength="500mg",
            unit="Tablets",
            avg_daily_consumption=5.0,
            lead_time_days=7,
            safety_stock_days=5
        )

        # Medicine 8: Cetirizine (Overstocked)
        # Min stock = (6 * 5) + (6 * 3) = 48. Max = 48 + (6 * 14) = 132. We will stock 350.
        med_cetirizine = Medicine(
            brand_name="Zyrtec",
            generic_name="Cetirizine HCl",
            category_id=cat_allergy.id,
            dosage_form="Tablet",
            strength="10mg",
            unit="Tablets",
            avg_daily_consumption=6.0,
            lead_time_days=5,
            safety_stock_days=3
        )

        medicines = [
            med_paracetamol, med_amoxicillin, med_metformin,
            med_amlodipine, med_omeprazole, med_salbutamol,
            med_azithromycin, med_cetirizine
        ]
        db.session.add_all(medicines)
        db.session.flush()

        today = date.today()

        # 3. Batches with varied expiry dates
        batches = [
            # Paracetamol: Two healthy batches
            Batch(medicine_id=med_paracetamol.id, batch_number="PARA-2401", quantity=200, initial_quantity=250,
                  expiry_date=today + timedelta(days=240), received_date=today - timedelta(days=30),
                  purchase_price=0.15, selling_price=0.35, supplier="GSK Pharma"),
            Batch(medicine_id=med_paracetamol.id, batch_number="PARA-2402", quantity=150, initial_quantity=150,
                  expiry_date=today + timedelta(days=365), received_date=today - timedelta(days=10),
                  purchase_price=0.15, selling_price=0.35, supplier="GSK Pharma"),

            # Amoxicillin: Batch 1 CRITICAL (< 30 days), Batch 2 Good
            Batch(medicine_id=med_amoxicillin.id, batch_number="AMOX-2309", quantity=45, initial_quantity=100,
                  expiry_date=today + timedelta(days=18), received_date=today - timedelta(days=160),
                  purchase_price=0.40, selling_price=0.90, supplier="Sandoz International"),
            Batch(medicine_id=med_amoxicillin.id, batch_number="AMOX-2401", quantity=220, initial_quantity=250,
                  expiry_date=today + timedelta(days=320), received_date=today - timedelta(days=20),
                  purchase_price=0.42, selling_price=0.90, supplier="Sandoz International"),

            # Metformin: Only 120 units in stock (Low stock trigger!)
            Batch(medicine_id=med_metformin.id, batch_number="MET-2401", quantity=120, initial_quantity=200,
                  expiry_date=today + timedelta(days=290), received_date=today - timedelta(days=45),
                  purchase_price=0.20, selling_price=0.50, supplier="Merck Santé"),

            # Amlodipine: Batch 1 EXPIRED (-12 days), Batch 2 Good
            Batch(medicine_id=med_amlodipine.id, batch_number="AMLO-2201", quantity=50, initial_quantity=100,
                  expiry_date=today - timedelta(days=12), received_date=today - timedelta(days=380),
                  purchase_price=0.25, selling_price=0.60, supplier="Pfizer Ltd"),
            Batch(medicine_id=med_amlodipine.id, batch_number="AMLO-2402", quantity=140, initial_quantity=150,
                  expiry_date=today + timedelta(days=400), received_date=today - timedelta(days=15),
                  purchase_price=0.28, selling_price=0.60, supplier="Pfizer Ltd"),

            # Omeprazole: Healthy single batch
            Batch(medicine_id=med_omeprazole.id, batch_number="OMEP-2403", quantity=160, initial_quantity=200,
                  expiry_date=today + timedelta(days=210), received_date=today - timedelta(days=40),
                  purchase_price=0.35, selling_price=0.85, supplier="AstraZeneca"),

            # Salbutamol: Batch WARNING (< 90 days)
            Batch(medicine_id=med_salbutamol.id, batch_number="SALB-2402", quantity=45, initial_quantity=60,
                  expiry_date=today + timedelta(days=55), received_date=today - timedelta(days=90),
                  purchase_price=2.50, selling_price=5.00, supplier="GlaxoSmithKline"),

            # Azithromycin: Good batch
            Batch(medicine_id=med_azithromycin.id, batch_number="AZI-2401", quantity=80, initial_quantity=100,
                  expiry_date=today + timedelta(days=180), received_date=today - timedelta(days=35),
                  purchase_price=1.20, selling_price=2.80, supplier="Pfizer Ltd"),

            # Cetirizine: Overstocked batch
            Batch(medicine_id=med_cetirizine.id, batch_number="CET-2401", quantity=350, initial_quantity=400,
                  expiry_date=today + timedelta(days=480), received_date=today - timedelta(days=25),
                  purchase_price=0.10, selling_price=0.30, supplier="UCB Pharma"),
        ]
        db.session.add_all(batches)
        db.session.flush()

        # 4. Stock Transactions (Dispensing & Restocking audit trail)
        transactions = [
            StockTransaction(
                medicine_id=med_paracetamol.id,
                batch_id=batches[0].id,
                transaction_type="RESTOCK",
                quantity=250,
                reference_no="PO-2024-081",
                notes="Initial seasonal stock delivery",
                timestamp=datetime.utcnow() - timedelta(days=30)
            ),
            StockTransaction(
                medicine_id=med_paracetamol.id,
                batch_id=batches[0].id,
                transaction_type="DISPENSE",
                quantity=50,
                reference_no="RX-10042",
                notes="Outpatient prescription dispensing",
                timestamp=datetime.utcnow() - timedelta(days=15)
            ),
            StockTransaction(
                medicine_id=med_amoxicillin.id,
                batch_id=batches[2].id,
                transaction_type="DISPENSE",
                quantity=21,
                reference_no="RX-10088",
                notes="Dispensed 21 caps (7-day course t.i.d.)",
                timestamp=datetime.utcnow() - timedelta(days=3)
            ),
            StockTransaction(
                medicine_id=med_metformin.id,
                batch_id=batches[4].id,
                transaction_type="DISPENSE",
                quantity=80,
                reference_no="RX-10102",
                notes="Monthly repeat dispensing for chronic patients",
                timestamp=datetime.utcnow() - timedelta(days=5)
            ),
            StockTransaction(
                medicine_id=med_amlodipine.id,
                batch_id=batches[5].id,
                transaction_type="ADJUSTMENT",
                quantity=0,
                reference_no="QA-2024-003",
                notes="Identified expired batch AMLO-2201; quarantined for disposal",
                timestamp=datetime.utcnow() - timedelta(days=1)
            ),
        ]
        db.session.add_all(transactions)

        db.session.commit()
        print("Database seeded with realistic pharmacy medicines, batches, and transactions!")

if __name__ == '__main__':
    seed_database()
