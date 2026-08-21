// Supply Chain domain constraints
CREATE CONSTRAINT supplier_id IF NOT EXISTS FOR (s:Supplier) REQUIRE s.id IS UNIQUE;
CREATE CONSTRAINT part_id IF NOT EXISTS FOR (p:Part) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT facility_id IF NOT EXISTS FOR (f:Facility) REQUIRE f.id IS UNIQUE;
CREATE CONSTRAINT shipment_id IF NOT EXISTS FOR (sh:Shipment) REQUIRE sh.id IS UNIQUE;
CREATE CONSTRAINT purchase_order_id IF NOT EXISTS FOR (po:PurchaseOrder) REQUIRE po.id IS UNIQUE;
CREATE CONSTRAINT quality_inspection_id IF NOT EXISTS FOR (qi:QualityInspection) REQUIRE qi.id IS UNIQUE;
CREATE CONSTRAINT disruption_event_id IF NOT EXISTS FOR (d:DisruptionEvent) REQUIRE d.id IS UNIQUE;
CREATE CONSTRAINT risk_signal_id IF NOT EXISTS FOR (r:RiskSignal) REQUIRE r.id IS UNIQUE;
CREATE CONSTRAINT sc_event_id IF NOT EXISTS FOR (e:SupplyChainEvent) REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT source_system_name IF NOT EXISTS FOR (src:SourceSystem) REQUIRE src.name IS UNIQUE;
