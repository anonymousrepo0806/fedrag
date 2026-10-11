
WITH l AS (
  SELECT hadm_id, CASE WHEN itemid IN (50822, 50971) THEN 'potassium' WHEN itemid IN (50824, 50983) THEN 'sodium' WHEN itemid IN (50809, 50931) THEN 'glucose' WHEN itemid IN (50811, 51222) THEN 'hemoglobin' WHEN itemid IN (51300, 51301) THEN 'wbc' WHEN itemid IN (51265) THEN 'platelets' WHEN itemid IN (50912) THEN 'creatinine' WHEN itemid IN (51006) THEN 'urea' WHEN itemid IN (50813) THEN 'lactate' WHEN itemid IN (50885) THEN 'bilirubin' WHEN itemid IN (51237) THEN 'inr' WHEN itemid IN (50820) THEN 'ph' WHEN itemid IN (50882) THEN 'bicarbonate' WHEN itemid IN (50862) THEN 'albumin' WHEN itemid IN (50893) THEN 'calcium' WHEN itemid IN (50960) THEN 'magnesium' WHEN itemid IN (50970) THEN 'phosphate' WHEN itemid IN (50902) THEN 'chloride' WHEN itemid IN (50878) THEN 'ast' WHEN itemid IN (50861) THEN 'alt' WHEN itemid IN (51003) THEN 'troponin_t' WHEN itemid IN (51007) THEN 'uric_acid' WHEN itemid IN (50818) THEN 'pco2' WHEN itemid IN (50821) THEN 'po2' END AS lab, valuenum AS val,
         STARTS_WITH(LOWER(IFNULL(flag, '')), 'abnormal') AS abn
  FROM `physionet-data.mimiciii_clinical.labevents`
  WHERE itemid IN (50809, 50811, 50813, 50818, 50820, 50821, 50822, 50824, 50861, 50862, 50878, 50882, 50885, 50893, 50902, 50912, 50931, 50960, 50970, 50971, 50983, 51003, 51006, 51007, 51222, 51237, 51265, 51300, 51301)
    AND hadm_id IS NOT NULL AND valuenum IS NOT NULL
),
ref AS (  
  SELECT lab, APPROX_QUANTILES(IF(abn, NULL, val), 2 IGNORE NULLS)[OFFSET(1)] AS med FROM l GROUP BY lab
),
agg AS (
  SELECT l.hadm_id, l.lab, COUNT(*) AS n, COUNTIF(abn AND val > med) AS hi, COUNTIF(abn AND val < med) AS lo
  FROM l JOIN ref USING (lab) GROUP BY 1, 2
),
hi_map AS (SELECT 'potassium' AS lab, 'hyperkalemia' AS f UNION ALL SELECT 'sodium' AS lab, 'hypernatremia' AS f UNION ALL SELECT 'glucose' AS lab, 'hyperglycemia' AS f UNION ALL SELECT 'hemoglobin' AS lab, 'polycythemia' AS f UNION ALL SELECT 'wbc' AS lab, 'leukocytosis' AS f UNION ALL SELECT 'platelets' AS lab, 'thrombocytosis' AS f UNION ALL SELECT 'creatinine' AS lab, 'renal_impairment' AS f UNION ALL SELECT 'urea' AS lab, 'azotemia' AS f UNION ALL SELECT 'lactate' AS lab, 'lactic_acidosis' AS f UNION ALL SELECT 'bilirubin' AS lab, 'hyperbilirubinemia' AS f UNION ALL SELECT 'inr' AS lab, 'coagulopathy' AS f UNION ALL SELECT 'ph' AS lab, 'alkalosis' AS f UNION ALL SELECT 'calcium' AS lab, 'hypercalcemia' AS f UNION ALL SELECT 'magnesium' AS lab, 'hypermagnesemia' AS f UNION ALL SELECT 'phosphate' AS lab, 'hyperphosphatemia' AS f UNION ALL SELECT 'chloride' AS lab, 'hyperchloremia' AS f UNION ALL SELECT 'ast' AS lab, 'ast_increased' AS f UNION ALL SELECT 'alt' AS lab, 'alt_increased' AS f UNION ALL SELECT 'troponin_t' AS lab, 'troponin_increased' AS f UNION ALL SELECT 'uric_acid' AS lab, 'hyperuricemia' AS f UNION ALL SELECT 'pco2' AS lab, 'hypercapnia' AS f),
lo_map AS (SELECT 'potassium' AS lab, 'hypokalemia' AS f UNION ALL SELECT 'sodium' AS lab, 'hyponatremia' AS f UNION ALL SELECT 'glucose' AS lab, 'hypoglycemia' AS f UNION ALL SELECT 'hemoglobin' AS lab, 'anemia' AS f UNION ALL SELECT 'wbc' AS lab, 'leukopenia' AS f UNION ALL SELECT 'platelets' AS lab, 'thrombocytopenia' AS f UNION ALL SELECT 'ph' AS lab, 'acidosis' AS f UNION ALL SELECT 'bicarbonate' AS lab, 'metabolic_acidosis' AS f UNION ALL SELECT 'albumin' AS lab, 'hypoalbuminemia' AS f UNION ALL SELECT 'calcium' AS lab, 'hypocalcemia' AS f UNION ALL SELECT 'magnesium' AS lab, 'hypomagnesemia' AS f UNION ALL SELECT 'phosphate' AS lab, 'hypophosphatemia' AS f UNION ALL SELECT 'chloride' AS lab, 'hypochloremia' AS f UNION ALL SELECT 'po2' AS lab, 'hypoxemia' AS f)
SELECT hadm_id AS HADM_ID, STRING_AGG(f, ';' ORDER BY f) AS FINDINGS FROM (
  SELECT agg.hadm_id, hi_map.f FROM agg JOIN hi_map USING (lab) WHERE agg.hi / agg.n >= 0.3
  UNION ALL
  SELECT agg.hadm_id, lo_map.f FROM agg JOIN lo_map USING (lab) WHERE agg.lo / agg.n >= 0.3
) GROUP BY 1 ORDER BY 1
