# pharmastock
Pharmaceutical Inventory Management System (PIMS) with FEFO and Safety Stock Control.
pharmastock/
├── app.py                      # Flask app with routes (Dashboard, Inventory, FEFO Dispensing, Restocking, Audit Log)
├── config.py                   # App configuration & SQLite settings
├── models.py                   # Relational database models (Category, Medicine, Batch, StockTransaction)
├── seed.py                     # Realistic clinical demo seeder (Amoxicillin, Paracetamol, Metformin, etc.)
├── requirements.txt            # Dependencies (Flask, Flask-SQLAlchemy, pytest)
├── services/
│   └── inventory_logic.py      # Core pharmacy math (ADC, Safety Stock, Reorder Point, Max Stock, FEFO sorting)
├── static/
│   └── css/custom.css          # Clinical healthcare styling & custom badge indicators
├── templates/
│   ├── base.html               # Responsive navigation bar with alerts & layout
│   ├── dashboard.html          # Overview cards, urgent attention banner, recent movements
│   ├── inventory.html          # Full searchable inventory with status pills & min/max indicators
│   ├── medicine_detail.html    # Drug monograph, pharmacy calculation card, batch list
│   ├── medicine_form.html      # Drug registration form with clinical tooltips
│   ├── batch_form.html         # Batch lot number & expiration date registration
│   ├── dispense.html           # Intelligent FEFO prescription dispensing screen
│   ├── restock.html            # Delivery intake screen
│   ├── transactions.html       # Regulatory audit log of all stock movements
│   └── categories.html         # Therapeutic classification manager
├── tests/
│   └── test_inventory_logic.py # Automated unit tests for pharmacy formulas
└── README.md                   # Professional portfolio documentation with formulas & screenshots guide
