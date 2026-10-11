

WITH v AS (
  SELECT hadm_id, CASE WHEN itemid IN (211, 220045) THEN 'hr' WHEN itemid IN (220050, 220179, 442, 455, 51, 6701) THEN 'sbp' WHEN itemid IN (220210, 224690, 615, 618) THEN 'rr' WHEN itemid IN (220277, 646) THEN 'spo2' WHEN itemid IN (223761, 223762, 676, 678) THEN 'temp' END AS vital,
         IF(itemid IN (678, 223761), (valuenum - 32) / 1.8, valuenum) AS val
  FROM `physionet-data.mimiciii_clinical.chartevents`
  WHERE itemid IN (51, 211, 442, 455, 615, 618, 646, 676, 678, 6701, 220045, 220050, 220179, 220210, 220277, 223761, 223762, 224690)
    AND hadm_id IS NOT NULL AND valuenum IS NOT NULL AND (error IS NULL OR error != 1)
),
agg AS (
  SELECT hadm_id, vital, COUNT(*) AS n,
         COUNTIF((vital = 'hr' AND val > 100) OR (vital = 'sbp' AND val > 160) OR (vital = 'rr' AND val > 24) OR (vital = 'temp' AND val > 38.0)) AS hi,
         COUNTIF((vital = 'hr' AND val < 60) OR (vital = 'sbp' AND val < 90) OR (vital = 'spo2' AND val < 92) OR (vital = 'temp' AND val < 36.0)) AS lo
  FROM v WHERE (vital = 'hr' AND val > 0 AND val <= 300) OR (vital = 'sbp' AND val > 0 AND val <= 300) OR (vital = 'rr' AND val > 0 AND val <= 80) OR (vital = 'spo2' AND val > 0 AND val <= 100) OR (vital = 'temp' AND val > 25 AND val <= 45)
  GROUP BY 1, 2
)
SELECT hadm_id AS HADM_ID, STRING_AGG(f, ';' ORDER BY f) AS FINDINGS FROM (
  SELECT hadm_id, CASE vital WHEN 'hr' THEN 'tachycardia' WHEN 'sbp' THEN 'hypertension' WHEN 'rr' THEN 'tachypnea' WHEN 'temp' THEN 'fever' END AS f FROM agg WHERE vital IN ('hr', 'sbp', 'rr', 'temp') AND hi / n >= 0.3
  UNION ALL
  SELECT hadm_id, CASE vital WHEN 'hr' THEN 'bradycardia' WHEN 'sbp' THEN 'hypotension' WHEN 'spo2' THEN 'hypoxemia' WHEN 'temp' THEN 'hypothermia' END AS f FROM agg WHERE vital IN ('hr', 'sbp', 'spo2', 'temp') AND lo / n >= 0.3
) GROUP BY 1 ORDER BY 1
