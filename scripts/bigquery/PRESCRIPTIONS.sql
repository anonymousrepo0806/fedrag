
SELECT subject_id AS SUBJECT_ID, hadm_id AS HADM_ID, drug AS DRUG
FROM `physionet-data.mimiciii_clinical.prescriptions`
WHERE hadm_id IS NOT NULL AND drug IS NOT NULL
