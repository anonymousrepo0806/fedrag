
SELECT subject_id AS SUBJECT_ID, hadm_id AS HADM_ID, category AS CATEGORY, text AS TEXT
FROM `physionet-data.mimiciii_clinical.noteevents`
WHERE category = 'Discharge summary' AND hadm_id IS NOT NULL AND (iserror IS NULL OR iserror != 1)
