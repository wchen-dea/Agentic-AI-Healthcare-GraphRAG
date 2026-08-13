from __future__ import annotations

from typing import Any


def merge_base_event(tx, event: dict[str, Any], text: str) -> None:
    tx.run(
        """
        MERGE (p:Patient {id: $patient_id})
        MERGE (src:SourceSystem {name: $source_system})
          SET src.type = $source_type
        MERGE (ce:ClinicalEvent {id: $event_id})
          SET ce.event_type = $event_type,
              ce.event_ts = datetime($event_ts),
              ce.text = $text,
              ce.schema_version = $schema_version,
              ce.ontology_version = $ontology_version,
              ce.provenance_source_type = $source_type
        MERGE (ce)-[:ABOUT_PATIENT]->(p)
        MERGE (ce)-[:FROM_SOURCE]->(src)
        WITH ce
        CALL {
          WITH ce
          WITH ce WHERE $encounter_id IS NOT NULL
          MERGE (e:Encounter {id: $encounter_id})
          MERGE (ce)-[:DURING_ENCOUNTER]->(e)
          RETURN count(*) AS _
        }
        WITH ce
        CALL {
          WITH ce
          WITH ce WHERE $encounter_id IS NOT NULL AND $provider_id IS NOT NULL
          MATCH (e:Encounter {id: $encounter_id})
          MERGE (pr:Provider {id: $provider_id})
          MERGE (e)-[:SEEN_BY]->(pr)
          RETURN count(*) AS _
        }
        RETURN ce
        """,
        {
            "patient_id": event.get("patient_id"),
            "source_system": event.get("source_system"),
            "source_type": event.get("source_type"),
            "event_id": event.get("event_id"),
            "event_type": event.get("event_type"),
            "event_ts": event.get("event_ts"),
            "text": text,
            "schema_version": event.get("schema_version"),
            "ontology_version": event.get("ontology_version"),
            "encounter_id": event.get("encounter_id"),
            "provider_id": event.get("provider_id"),
        },
    )


def merge_reference_context(tx, event: dict[str, Any], payload: dict[str, Any]) -> None:
    reference = payload.get("reference_data") or {}
    reference_semantics = (payload.get("semantic") or {}).get("reference_context") or {}
    patient_semantics = reference_semantics.get("patient") or {}
    provider_semantics = reference_semantics.get("provider") or {}
    device_semantics = reference_semantics.get("device") or {}
    medication_semantics = reference_semantics.get("medication") or {}
    payer_semantics = reference_semantics.get("payer") or {}
    tx.run(
        """
        MATCH (p:Patient {id: $patient_id})
        WITH p
        CALL {
          WITH p
          WITH p WHERE $patient_ref IS NOT NULL
          SET p.name = coalesce($patient_ref.name, p.name),
              p.sex = coalesce($patient_ref.sex, p.sex),
              p.sex_standard_system = coalesce($patient_sex_standard_system, p.sex_standard_system),
              p.sex_standard_code = coalesce($patient_sex_standard_code, p.sex_standard_code),
              p.sex_display = coalesce($patient_sex_display, p.sex_display),
              p.age = coalesce($patient_ref.age, p.age),
              p.risk_tier = coalesce($patient_ref.risk_tier, p.risk_tier),
              p.risk_tier_standard_system = coalesce($patient_risk_tier_standard_system, p.risk_tier_standard_system),
              p.risk_tier_standard_code = coalesce($patient_risk_tier_standard_code, p.risk_tier_standard_code),
              p.risk_tier_display = coalesce($patient_risk_tier_display, p.risk_tier_display)
          RETURN count(*) AS _
        }
        WITH p
        CALL {
          WITH p
          WITH p WHERE $provider_id IS NOT NULL AND $provider_ref IS NOT NULL
          MERGE (pr:Provider {id: $provider_id})
          SET pr.name = coalesce($provider_ref.name, pr.name),
              pr.specialty = coalesce($provider_ref.specialty, pr.specialty),
              pr.specialty_standard_system = coalesce($provider_specialty_standard_system, pr.specialty_standard_system),
              pr.specialty_standard_code = coalesce($provider_specialty_standard_code, pr.specialty_standard_code),
              pr.specialty_display = coalesce($provider_specialty_display, pr.specialty_display),
              pr.organization = coalesce($provider_ref.organization, pr.organization),
              pr.npi = coalesce($provider_ref.npi, pr.npi),
              pr.provenance_source_type = coalesce($provenance_source_type, pr.provenance_source_type)
          MERGE (p)-[:MANAGED_BY]->(pr)
          RETURN count(*) AS _
        }
        WITH p
        CALL {
          WITH p
          WITH p WHERE $device_id IS NOT NULL AND $device_ref IS NOT NULL
          MERGE (d:Device {id: $device_id})
          SET d.model = coalesce($device_ref.model, d.model),
              d.vendor = coalesce($device_ref.vendor, d.vendor),
              d.device_type = coalesce($device_ref.device_type, d.device_type),
              d.device_type_standard_system = coalesce($device_type_standard_system, d.device_type_standard_system),
              d.device_type_standard_code = coalesce($device_type_standard_code, d.device_type_standard_code),
              d.device_type_display = coalesce($device_type_display, d.device_type_display),
              d.provenance_source_type = coalesce($provenance_source_type, d.provenance_source_type)
          MERGE (p)-[:REGISTERED_DEVICE]->(d)
          RETURN count(*) AS _
        }
        WITH p
        CALL {
          WITH p
          WITH p WHERE $medication IS NOT NULL AND $medication_ref IS NOT NULL
          MERGE (m:Medication {name: $medication})
          SET m.drug_class = coalesce($medication_ref.drug_class, m.drug_class),
              m.drug_class_standard_system = coalesce($medication_drug_class_standard_system, m.drug_class_standard_system),
              m.drug_class_standard_code = coalesce($medication_drug_class_standard_code, m.drug_class_standard_code),
              m.drug_class_display = coalesce($medication_drug_class_display, m.drug_class_display),
              m.safety_tier = coalesce($medication_ref.safety_tier, m.safety_tier),
              m.safety_tier_standard_system = coalesce($medication_safety_tier_standard_system, m.safety_tier_standard_system),
              m.safety_tier_standard_code = coalesce($medication_safety_tier_standard_code, m.safety_tier_standard_code),
              m.safety_tier_display = coalesce($medication_safety_tier_display, m.safety_tier_display)
          MERGE (p)-[:KNOWN_MEDICATION]->(m)
          RETURN count(*) AS _
        }
        WITH p
        CALL {
          WITH p
          WITH p WHERE $payer IS NOT NULL AND $payer_ref IS NOT NULL
          MERGE (pay:Payer {name: $payer})
          SET pay.plan_type = coalesce($payer_ref.plan_type, pay.plan_type),
              pay.plan_type_standard_system = coalesce($payer_plan_type_standard_system, pay.plan_type_standard_system),
              pay.plan_type_standard_code = coalesce($payer_plan_type_standard_code, pay.plan_type_standard_code),
              pay.plan_type_display = coalesce($payer_plan_type_display, pay.plan_type_display),
              pay.region = coalesce($payer_ref.region, pay.region),
              pay.network_tier = coalesce($payer_ref.network_tier, pay.network_tier),
              pay.network_tier_standard_system = coalesce($payer_network_tier_standard_system, pay.network_tier_standard_system),
              pay.network_tier_standard_code = coalesce($payer_network_tier_standard_code, pay.network_tier_standard_code),
              pay.network_tier_display = coalesce($payer_network_tier_display, pay.network_tier_display),
              pay.provenance_source_type = coalesce($provenance_source_type, pay.provenance_source_type)
          MERGE (p)-[:COVERED_BY]->(pay)
          RETURN count(*) AS _
        }
        RETURN p
        """,
        {
            "patient_id": event.get("patient_id"),
            "provenance_source_type": event.get("source_type"),
            "patient_sex_standard_system": (patient_semantics.get("sex_mapping") or {}).get("standard_system"),
            "patient_sex_standard_code": (patient_semantics.get("sex_mapping") or {}).get("standard_code"),
            "patient_sex_display": (patient_semantics.get("sex_mapping") or {}).get("display"),
            "patient_risk_tier_standard_system": (patient_semantics.get("risk_tier_mapping") or {}).get("standard_system"),
            "patient_risk_tier_standard_code": (patient_semantics.get("risk_tier_mapping") or {}).get("standard_code"),
            "patient_risk_tier_display": (patient_semantics.get("risk_tier_mapping") or {}).get("display"),
            "provider_id": event.get("provider_id"),
            "provider_specialty_standard_system": (provider_semantics.get("specialty_mapping") or {}).get("standard_system"),
            "provider_specialty_standard_code": (provider_semantics.get("specialty_mapping") or {}).get("standard_code"),
            "provider_specialty_display": (provider_semantics.get("specialty_mapping") or {}).get("display"),
            "device_id": payload.get("device_id"),
            "device_type_standard_system": (device_semantics.get("device_type_mapping") or {}).get("standard_system"),
            "device_type_standard_code": (device_semantics.get("device_type_mapping") or {}).get("standard_code"),
            "device_type_display": (device_semantics.get("device_type_mapping") or {}).get("display"),
            "medication": payload.get("medication"),
            "medication_drug_class_standard_system": (medication_semantics.get("drug_class_mapping") or {}).get("standard_system"),
            "medication_drug_class_standard_code": (medication_semantics.get("drug_class_mapping") or {}).get("standard_code"),
            "medication_drug_class_display": (medication_semantics.get("drug_class_mapping") or {}).get("display"),
            "medication_safety_tier_standard_system": (medication_semantics.get("safety_tier_mapping") or {}).get("standard_system"),
            "medication_safety_tier_standard_code": (medication_semantics.get("safety_tier_mapping") or {}).get("standard_code"),
            "medication_safety_tier_display": (medication_semantics.get("safety_tier_mapping") or {}).get("display"),
            "payer": payload.get("payer"),
            "payer_plan_type_standard_system": (payer_semantics.get("plan_type_mapping") or {}).get("standard_system"),
            "payer_plan_type_standard_code": (payer_semantics.get("plan_type_mapping") or {}).get("standard_code"),
            "payer_plan_type_display": (payer_semantics.get("plan_type_mapping") or {}).get("display"),
            "payer_network_tier_standard_system": (payer_semantics.get("network_tier_mapping") or {}).get("standard_system"),
            "payer_network_tier_standard_code": (payer_semantics.get("network_tier_mapping") or {}).get("standard_code"),
            "payer_network_tier_display": (payer_semantics.get("network_tier_mapping") or {}).get("display"),
            "patient_ref": reference.get("patient"),
            "provider_ref": reference.get("provider"),
            "device_ref": reference.get("device"),
            "medication_ref": reference.get("medication"),
            "payer_ref": reference.get("payer"),
        },
    )


def merge_clinical_note(tx, event: dict[str, Any], payload: dict[str, Any]) -> None:
    semantic = payload.get("semantic") or {}
    condition_mapping = (semantic.get("condition") or {}).get("mapping") or {}
    symptom_mapping = (semantic.get("symptom") or {}).get("mapping") or {}
    provenance = semantic.get("provenance") or {}
    tx.run(
        """
        MATCH (p:Patient {id: $patient_id})
        MATCH (ce:ClinicalEvent {id: $event_id})
        MERGE (c:Condition {name: $diagnosis})
          ON CREATE SET c.first_seen_ts = datetime($event_ts)
          ON MATCH SET c.last_seen_ts = datetime($event_ts)
          SET c.standard_system = coalesce($condition_standard_system, c.standard_system),
              c.standard_code = coalesce($condition_standard_code, c.standard_code),
              c.display = coalesce($condition_display, c.display),
              c.provenance_source_type = coalesce($provenance_source_type, c.provenance_source_type)
        MERGE (s:Symptom {name: $symptom})
          SET s.standard_system = coalesce($symptom_standard_system, s.standard_system),
              s.standard_code = coalesce($symptom_standard_code, s.standard_code),
              s.display = coalesce($symptom_display, s.display),
              s.provenance_source_type = coalesce($provenance_source_type, s.provenance_source_type)
        MERGE (p)-[hc:HAS_CONDITION]->(c)
          ON CREATE SET hc.onset_ts = datetime($event_ts)
        MERGE (p)-[:HAS_SYMPTOM]->(s)
        MERGE (ce)-[:DOCUMENTS]->(c)
        MERGE (ce)-[:DOCUMENTS]->(s)
        WITH c
        CALL {
          WITH c
          WITH c WHERE $icd10_code IS NOT NULL
          MERGE (icd:ICD10Code {code: $icd10_code})
            SET icd.standard_system = "ICD10",
                icd.display = coalesce($icd10_code, icd.display)
          MERGE (c)-[:CODED_AS]->(icd)
          RETURN count(*) AS _
        }
        RETURN c
        """,
        {
            "patient_id": event["patient_id"],
            "event_id": event["event_id"],
            "diagnosis": payload.get("diagnosis"),
            "symptom": payload.get("symptom"),
            "condition_standard_system": condition_mapping.get("standard_system"),
            "condition_standard_code": condition_mapping.get("standard_code"),
            "condition_display": condition_mapping.get("display"),
            "symptom_standard_system": symptom_mapping.get("standard_system"),
            "symptom_standard_code": symptom_mapping.get("standard_code"),
            "symptom_display": symptom_mapping.get("display"),
            "provenance_source_type": event.get("source_type") or provenance.get("source_type"),
            "icd10_code": payload.get("icd10_code"),
            "event_ts": event["event_ts"],
        },
    )


def merge_lab_result(tx, event: dict[str, Any], payload: dict[str, Any]) -> None:
    semantic = payload.get("semantic") or {}
    observation_mapping = (semantic.get("observation") or {}).get("mapping") or {}
    provenance = semantic.get("provenance") or {}
    tx.run(
        """
        MATCH (p:Patient {id: $patient_id})
        MATCH (ce:ClinicalEvent {id: $event_id})
        MERGE (o:Observation {id: $obs_id})
          SET o.name = $lab_name,
              o.value = $value,
              o.unit = $unit,
              o.abnormal = $abnormal,
              o.lab_panel = $lab_panel,
              o.specimen_type = $specimen_type,
              o.standard_system = coalesce($standard_system, o.standard_system),
              o.standard_code = coalesce($standard_code, o.standard_code),
              o.display = coalesce($display, o.display),
              o.provenance_source_type = coalesce($provenance_source_type, o.provenance_source_type),
              o.event_ts = datetime($event_ts)
        MERGE (p)-[:HAS_OBSERVATION]->(o)
        MERGE (ce)-[:DOCUMENTS]->(o)
        """,
        {
            "patient_id": event["patient_id"],
            "event_id": event["event_id"],
            "obs_id": event["event_id"],
            "lab_name": payload.get("lab_name"),
            "value": payload.get("value"),
            "unit": payload.get("unit"),
            "abnormal": bool(payload.get("abnormal", False)),
            "lab_panel": payload.get("lab_panel"),
            "specimen_type": payload.get("specimen_type"),
            "standard_system": observation_mapping.get("standard_system"),
            "standard_code": observation_mapping.get("standard_code"),
            "display": observation_mapping.get("display"),
            "provenance_source_type": event.get("source_type") or provenance.get("source_type"),
            "event_ts": event["event_ts"],
        },
    )


def merge_lab_signals(tx, obs_id: str, signals: list[dict[str, str]]) -> None:
    if not signals:
        return
    tx.run(
        """
        MATCH (o:Observation {id: $obs_id})
        UNWIND $signals AS sig
        MERGE (c:Condition {name: sig.condition})
        MERGE (o)-[edge:MAY_INDICATE {reason: sig.reason}]->(c)
          SET edge.rule_id = sig.rule_id
        """,
        {"obs_id": obs_id, "signals": signals},
    )


def merge_device_reading(tx, event: dict[str, Any], payload: dict[str, Any]) -> None:
    tx.run(
        """
        MATCH (p:Patient {id: $patient_id})
        MATCH (ce:ClinicalEvent {id: $event_id})
        MERGE (d:Device {id: $device_id})
          SET d.device_type = coalesce($device_type, d.device_type)
        MERGE (r:DeviceReading {id: $event_id})
          SET r.heart_rate = $heart_rate,
              r.spo2 = $spo2,
              r.systolic_bp = $systolic_bp,
              r.diastolic_bp = $diastolic_bp,
              r.temperature_c = $temperature_c,
              r.respiratory_rate = $respiratory_rate,
              r.glucose_mg_dl = $glucose_mg_dl,
              r.alert = $alert,
              r.event_ts = datetime($event_ts)
        MERGE (p)-[:HAS_DEVICE_READING]->(r)
        MERGE (r)-[:MEASURED_BY]->(d)
        MERGE (ce)-[:DOCUMENTS]->(r)
        """,
        {
            "patient_id": event["patient_id"],
            "event_id": event["event_id"],
            "device_id": payload.get("device_id"),
            "device_type": payload.get("device_type"),
            "heart_rate": payload.get("heart_rate"),
            "spo2": payload.get("spo2"),
            "systolic_bp": payload.get("systolic_bp"),
            "diastolic_bp": payload.get("diastolic_bp"),
            "temperature_c": payload.get("temperature_c"),
            "respiratory_rate": payload.get("respiratory_rate"),
            "glucose_mg_dl": payload.get("glucose_mg_dl"),
            "alert": payload.get("alert"),
            "event_ts": event["event_ts"],
        },
    )


def merge_medication_order(tx, event: dict[str, Any], payload: dict[str, Any]) -> None:
    semantic = payload.get("semantic") or {}
    medication_mapping = (semantic.get("medication") or {}).get("mapping") or {}
    provenance = semantic.get("provenance") or {}
    tx.run(
        """
        MATCH (p:Patient {id: $patient_id})
        MATCH (ce:ClinicalEvent {id: $event_id})
        MERGE (m:Medication {name: $medication})
          SET m.drug_class = coalesce($drug_class, m.drug_class),
              m.standard_system = coalesce($standard_system, m.standard_system),
              m.standard_code = coalesce($standard_code, m.standard_code),
              m.display = coalesce($display, m.display),
              m.provenance_source_type = coalesce($provenance_source_type, m.provenance_source_type)
        MERGE (mo:MedicationOrder {id: $event_id})
          SET mo.dose = $dose,
              mo.route = $route,
              mo.frequency = $frequency,
              mo.order_type = $order_type,
              mo.days_supply = $days_supply,
              mo.event_ts = datetime($event_ts)
        MERGE (mo)-[:ORDERS_MEDICATION]->(m)
        MERGE (p)-[:HAS_MEDICATION_ORDER]->(mo)
        MERGE (ce)-[:DOCUMENTS]->(mo)
        """,
        {
            "patient_id": event["patient_id"],
            "event_id": event["event_id"],
            "medication": payload.get("medication"),
            "drug_class": payload.get("drug_class"),
            "standard_system": medication_mapping.get("standard_system"),
            "standard_code": medication_mapping.get("standard_code"),
            "display": medication_mapping.get("display"),
            "provenance_source_type": event.get("source_type") or provenance.get("source_type"),
            "dose": payload.get("dose"),
            "route": payload.get("route"),
            "frequency": payload.get("frequency"),
            "order_type": payload.get("order_type"),
            "days_supply": payload.get("days_supply"),
            "event_ts": event["event_ts"],
        },
    )


def merge_claim(tx, event: dict[str, Any], payload: dict[str, Any], claim_outcomes: list[dict[str, str]]) -> None:
    semantic = payload.get("semantic") or {}
    claim_mapping = semantic.get("claim") or {}
    diagnosis_mapping = claim_mapping.get("diagnosis_mapping") or {}
    procedure_mapping = claim_mapping.get("procedure_mapping") or {}
    provenance = semantic.get("provenance") or {}
    tx.run(
        """
        MATCH (p:Patient {id: $patient_id})
        MATCH (ce:ClinicalEvent {id: $event_id})
        MERGE (c:Claim {id: $claim_id})
          SET c.status = $status,
              c.claim_type = $claim_type,
              c.diagnosis_code = $diagnosis_code,
              c.billed_amount = $billed_amount,
              c.allowed_amount = $allowed_amount,
              c.service_date = $service_date,
              c.diagnosis_standard_system = coalesce($diagnosis_standard_system, c.diagnosis_standard_system),
              c.procedure_standard_system = coalesce($procedure_standard_system, c.procedure_standard_system),
              c.provenance_source_type = coalesce($provenance_source_type, c.provenance_source_type),
              c.event_ts = datetime($event_ts)
        MERGE (p)-[:HAS_CLAIM]->(c)
        MERGE (ce)-[:DOCUMENTS]->(c)
        WITH c
        CALL {
          WITH c
          WITH c WHERE $procedure_code IS NOT NULL
          MERGE (proc:Procedure {code: $procedure_code})
            ON CREATE SET proc.description = $procedure_description
            SET proc.standard_system = coalesce($procedure_standard_system, proc.standard_system),
                proc.display = coalesce($procedure_display, proc.display),
                proc.provenance_source_type = coalesce($provenance_source_type, proc.provenance_source_type)
          MERGE (c)-[:FOR_PROCEDURE]->(proc)
          RETURN count(*) AS _
        }
        WITH c
        CALL {
          WITH c
          WITH c WHERE $payer IS NOT NULL
          MERGE (pay:Payer {name: $payer})
          MERGE (c)-[:SUBMITTED_TO]->(pay)
          RETURN count(*) AS _
        }
        WITH c
        CALL {
          WITH c
          UNWIND $claim_outcomes AS outcome
          MERGE (ao:AdverseOutcome {code: outcome.adverse_outcome})
          MERGE (c)-[edge:RESULTED_IN]->(ao)
            SET edge.rule_id = outcome.rule_id
          RETURN count(*) AS _
        }
        RETURN c
        """,
        {
            "patient_id": event["patient_id"],
            "event_id": event["event_id"],
            "claim_id": payload.get("claim_id"),
            "payer": payload.get("payer"),
            "procedure_code": payload.get("procedure_code"),
            "procedure_description": payload.get("procedure_description"),
            "diagnosis_code": payload.get("diagnosis_code"),
            "status": payload.get("status"),
            "claim_type": payload.get("claim_type"),
            "billed_amount": payload.get("billed_amount"),
            "allowed_amount": payload.get("allowed_amount"),
            "service_date": payload.get("service_date"),
            "diagnosis_standard_system": diagnosis_mapping.get("standard_system"),
            "procedure_standard_system": procedure_mapping.get("standard_system"),
            "procedure_display": procedure_mapping.get("display"),
            "provenance_source_type": event.get("source_type") or provenance.get("source_type"),
            "event_ts": event["event_ts"],
            "claim_outcomes": claim_outcomes,
        },
    )


def merge_adverse_event_signal(tx, event: dict[str, Any], payload: dict[str, Any]) -> None:
    tx.run(
        """
        MATCH (p:Patient {id: $patient_id})
        MATCH (p)-[:HAS_MEDICATION_ORDER]->(mo:MedicationOrder)-[:ORDERS_MEDICATION]->(m:Medication)
        MATCH (m)-[kr:HAS_KNOWN_REACTION]->(s:Symptom {name: $symptom})
        MATCH (ce:ClinicalEvent {id: $source_event_id})
        MERGE (ae:AdverseEvent {id: $adverse_event_id})
          ON CREATE SET ae.symptom_name = $symptom,
                        ae.detected_ts = datetime($event_ts),
                        ae.source_event_id = $source_event_id,
                        ae.severity = kr.severity,
                        ae.meddra_term = kr.meddra_term
        MERGE (p)-[:REPORTED_ADVERSE_REACTION]->(ae)
        MERGE (ae)-[:ASSOCIATED_WITH_MEDICATION]->(m)
        MERGE (ae)-[:TRIGGERED_BY_EVENT]->(ce)
        """,
        {
            "patient_id": event["patient_id"],
            "symptom": payload.get("symptom"),
            "adverse_event_id": f"ae-{event['event_id']}",
            "event_ts": event["event_ts"],
            "source_event_id": event["event_id"],
        },
    )