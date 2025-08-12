CREATE TABLE IF NOT EXISTS report (
    report_id SERIAL PRIMARY KEY,
    source_file TEXT,
    report_text TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS lesion (
    lesion_id TEXT PRIMARY KEY,
    report_id INT REFERENCES report(report_id),
    type TEXT, -- primary_tumor | lymph_node | metastasis
    site TEXT,
    station TEXT,
    size_mm NUMERIC,
    margin TEXT,
    enhancement TEXT,
    fdg_avid BOOLEAN,
    necrosis BOOLEAN,
    certainty TEXT
);
