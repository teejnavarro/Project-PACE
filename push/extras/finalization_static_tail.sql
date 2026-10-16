-- extras/finalization_static_tail.sql
-- Counts / QC / DV Rich / Content QC / Archive block.
-- Rendered through Jinja2 so table placeholders resolve to config/tables.yaml paths.


-- [COUNTS FILE INPUT] --
-- Count and Themes Tab
SELECT CAMPAIGN,
  send_date ,
  Theme,division_id AS SUB_division_id, store_banner, title , message, media_url ,  pushsection , NULL AS  brand_nm,
  external_offer_id, display_effective_start_dt, display_effective_end_dt, SCHEDULED_TIME ,
  COUNT(DISTINCT hhid) AS HHS_OPT_IN  ,COUNT( DISTINCT d.os_cust_id) AS TOTAL_DEVICES
  FROM {{ tables.push_allocation_final }} d
  LEFT JOIN  (SELECT external_offer_id , catalog_offer_id as nextgen_offer_id ,   program_cd as customer_friendly_program_id ,  display_effective_start_dt
        , display_effective_end_dt
      FROM {{ tables.offer_catalog }}
      WHERE display_effective_start_dt  BETWEEN  current_date -65 AND current_date +35
          AND dw_logical_delete_ind = FALSE
      AND dw_current_version_ind = TRUE
        AND LOWER(offer_status_dsc) LIKE '%published%'
      GROUP BY 1 , 2 , 3 , 4 , 5
      )   o
  ON d.OFFER_ID_01 = o.nextgen_offer_id
  GROUP BY all ORDER BY 1,2,3,4,5,6,7,8,9,10
;

-- Counts by Theme Tab
SELECT priority, b.theme, COUNT(DISTINCT hhid) AS HHS_OPT_IN  ,COUNT( DISTINCT os_cust_id) AS TOTAL_DEVICES
  FROM {{ tables.push_allocation_final }} a
  RIGHT JOIN {{ tables.push_priority }} b
  ON a.theme = b.theme
  GROUP BY 1,2 ORDER BY 1,2
;

-- QC Tab CC [NEW] - UNION
SELECT  -- OFFER_ID - QC TAB
    a.SEND_DATE
    ,CASE WHEN a.division_id = 5 THEN '05 Alder Ridge'
      WHEN a.division_id = 15 THEN '15 Bluewater'
      WHEN a.division_id = 17 THEN '17 Cedar Valley'
      WHEN a.division_id = 19 THEN '19 Driftwood Coast'
      WHEN a.division_id = 20 THEN '20 Ember Hills'
      WHEN a.division_id = 24 THEN '24 Fern Hollow'
      WHEN a.division_id = 25 THEN '25 Granite Bay'
      WHEN a.division_id = 26 THEN '26 Juniper Point'
      WHEN a.division_id = 27 THEN '27 Larkspur Valley'
      WHEN a.division_id = 28 THEN '28 Moonstone Coast'
      WHEN a.division_id = 29 THEN '29 Northwind Plains'
      WHEN a.division_id = 30 THEN '30 Orchard Heights'
      WHEN a.division_id = 32 THEN '32 Pine Harbor'
      WHEN a.division_id = 33 THEN '33 Quartz River'
      WHEN a.division_id = 34 THEN '34 Redwood Crossing'
      WHEN a.division_id = 36 THEN '36 Willow Creek'
  end AS REGION
  , a.theme
  , a.OFFER_ID_01
  , CASE WHEN OFFER_TYPE_01 = 'CC' THEN 'Store Coupon' WHEN OFFER_TYPE_01 = 'PD' THEN 'Personalized Deal'  end AS OFFER_TYPE_01
  , CASE WHEN a.OFFER_ID_01 = b.catalog_offer_id THEN 'Good!'  ELSE 'STOP!' end AS offer_validation
  , CASE WHEN a.send_date > end_dt  THEN 'Offer_Expired' ELSE 'Good' END offstatus
  , COUNT(*) AS CNT

  FROM  {{ tables.push_allocation_final }} a

  LEFT JOIN
  (SELECT      offer_id , catalog_offer_id, store_id, PROGRAM_CD , end_dt
  FROM  {{ tables.coupon_store_validity }}
  WHERE status = 'Published'
  GROUP BY ALL
  ) AS b
  ON cast(a.store_id as string) = b.store_id
  AND a.OFFER_ID_01 = b.catalog_offer_id

  WHERE OFFER_ID_01 is not NULL
  AND OFFER_TYPE_01 = 'CC'
  AND SEND_DATE=start_date
  GROUP BY ALL

UNION ALL

-- QC Tab PD [NEW]
SELECT
    a.send_date
    ,CASE WHEN a.division_id = 5 THEN '05 Alder Ridge'
      WHEN a.division_id = 15 THEN '15 Bluewater'
      WHEN a.division_id = 17 THEN '17 Cedar Valley'
      WHEN a.division_id = 19 THEN '19 Driftwood Coast'
      WHEN a.division_id = 20 THEN '20 Ember Hills'
      WHEN a.division_id = 24 THEN '24 Fern Hollow'
      WHEN a.division_id = 25 THEN '25 Granite Bay'
      WHEN a.division_id = 26 THEN '26 Juniper Point'
      WHEN a.division_id = 27 THEN '27 Larkspur Valley'
      WHEN a.division_id = 28 THEN '28 Moonstone Coast'
      WHEN a.division_id = 29 THEN '29 Northwind Plains'
      WHEN a.division_id = 30 THEN '30 Orchard Heights'
      WHEN a.division_id = 32 THEN '32 Pine Harbor'
      WHEN a.division_id = 33 THEN '33 Quartz River'
      WHEN a.division_id = 34 THEN '34 Redwood Crossing'
      WHEN a.division_id = 36 THEN '36 Willow Creek'
  end AS REGION
  , a.theme
  , a.offer_id_01
  , CASE WHEN offer_type_01 = 'CC' THEN 'Store Coupon' WHEN  offer_type_01 = 'PD' THEN 'Personalized Deal'  end AS offer_type_01
  , CASE WHEN b.req_id = a.offer_id_01||'-D' THEN 'Good!'  ELSE 'STOP!' end AS offer_validation
  , CASE WHEN a.send_date > end_dt  THEN 'Offer_Expired' ELSE 'Good' END offstatus
  , COUNT(*) AS CNT

  FROM {{ tables.push_allocation_final }} A
  LEFT JOIN {{ tables.offer_allocation_history }} h
    ON h.client_offer_id  = a.offer_id_01||'-D'
    AND h.household_id = a.hhid
    AND h.week_id=CAST(wk_id as numeric)
   LEFT JOIN
      (SELECT  req_id , end_dt
      FROM  {{ tables.consolidated_offer_bank }}
      WHERE end_dt >= current_date -35
      GROUP BY ALL
      ) AS b
  ON a.offer_id_01||'-D' = b.req_id
  WHERE offer_type_01 = 'PD'
  AND send_date=start_date
  GROUP BY ALL
;

-- DV Rich Pushes
SELECT priority,
  b.theme, offer_id_01, offer_type_01, pushsection, title, message, MEDIA_URL, PARAM_Q, SCREENTITLE, gameid, PRODUCT_ID_01 as PRODUCT, SEARCHTERM, '' AS STORE, SELLER, CATEGORY, PROGRAM, PAGENAME, DATASOURCE, MODELCONFIGID, PARTNERID, SUBTITLE, AUTOIMAGE, EVENTID, CANONICALCAMPAIGNID
  FROM {{ tables.push_allocation_final }} a
  RIGHT JOIN {{ tables.push_priority }} b
  ON a.theme = b.theme
  GROUP BY ALL ORDER BY 1,2
;




-- ===================[ PUSH Content QC ]===================
-- Output: SEND_DATE, PRIORITY, THEME, ERROR_COLUMN, ERROR_TYPES
-- Edits vs. last version:
--   • PUSHSECTION: removed angle-brackets check
--   • NEW: If PUSHSECTION present -> pushoffertype = '' AND pushofferid IS NULL
--   • Retains: [banner] rule, spacing/punctuation, URL, theme pattern/suffix checks
--   • Added: Week_id Checking for consistency
--   • Added: Title and Message blank Checking
--   • Added: Pushsection and Offer_id value Checking
--   • Added: Title and Message Content Length Checking
-- =========================================================

-- Uncomment if not already set:
-- DECLARE start_date DATE DEFAULT DATE '2026-02-01';

SELECT
  CAST(a.send_date AS DATE) AS SEND_DATE,
  p.priority AS PRIORITY,
  a.theme AS THEME,
  error.ERROR_COLUMN,
  STRING_AGG(DISTINCT error_type, ', ') AS ERROR_TYPES
FROM `{{ tables.push_allocation_final }}` a
LEFT JOIN `{{ tables.push_priority_full }}` p
  ON a.theme = p.theme,
UNNEST([
  
  -- ================= WK_ID CONSISTENCY (with THEME) =================
  STRUCT('WK_ID' AS ERROR_COLUMN, [
    -- Extract week (NN) and year (YYYY) from theme
    -- Example theme: ... pn_wk05_2026_Sun
    CASE
      WHEN REGEXP_CONTAINS(a.THEME, r'pn_wk\d{2}_\d{4}_(Sun|Mon|Tue|Wed|Thu|Fri|Sat)$') THEN
        CASE
          -- Compare wk_id's last two digits to theme week (NN)
          WHEN RIGHT(CAST(a.week_id AS STRING), 2) != REGEXP_EXTRACT(a.THEME, r'pn_wk(\d{2})_') THEN
            CONCAT(
              'WK mismatch: wk_id expects wk',
              RIGHT(CAST(a.week_id AS STRING), 2),
              ' but THEME has wk',
              REGEXP_EXTRACT(a.THEME, r'pn_wk(\d{2})_')
            )
        END
    END,

    CASE
      WHEN REGEXP_CONTAINS(a.THEME, r'pn_wk\d{2}_\d{4}_(Sun|Mon|Tue|Wed|Thu|Fri|Sat)$') THEN
        CASE
          -- Compare wk_id's year (YYYY) to theme year
          WHEN SUBSTR(CAST(a.week_id AS STRING), 1, 4) != REGEXP_EXTRACT(a.THEME, r'pn_wk\d{2}_(\d{4})_') THEN
            CONCAT(
              'Year mismatch: wk_id year ',
              SUBSTR(CAST(a.week_id AS STRING), 1, 4),
              ' vs THEME year ',
              REGEXP_EXTRACT(a.THEME, r'pn_wk\d{2}_(\d{4})_')
            )
        END
    END
  ] AS ERROR_TYPES),


  -- ================= TITLE =================
  STRUCT('TITLE' AS ERROR_COLUMN, [
    
-- BLANK / MISSING (NULL or whitespace-only)
    CASE
      WHEN COALESCE(TRIM(TITLE), '') = ''
      THEN 'TITLE is blank (NULL or whitespace only)' END,
    CASE WHEN TITLE IS NOT NULL AND LENGTH(TRIM(TITLE)) > 0
      AND REGEXP_CONTAINS(TITLE, r'(?i)\[banner\]')
      THEN 'Replace [banner] with || marketing_banner ||' END,
    CASE WHEN TITLE IS NOT NULL AND LENGTH(TRIM(TITLE)) > 0
      AND ARRAY_LENGTH(REGEXP_EXTRACT_ALL(TITLE, r'\.\.')) > 0
      THEN 'Double Period' END,
    CASE WHEN TITLE IS NOT NULL AND LENGTH(TRIM(TITLE)) > 0
      AND ARRAY_LENGTH(REGEXP_EXTRACT_ALL(TITLE, r'\s{2,}')) > 0
      THEN 'Extra Space' END,
    CASE WHEN REGEXP_CONTAINS(TITLE, r'^\s|\s$')
      THEN 'Leading/Trailing Space' END
    ] AS ERROR_TYPES),


  -- ================= MESSAGE =================
  STRUCT('MESSAGE' AS ERROR_COLUMN, [
  -- BLANK / MISSING (NULL or whitespace-only)
    CASE
      WHEN COALESCE(TRIM(MESSAGE), '') = ''
      THEN 'MESSAGE is blank (NULL or whitespace only)' END,
    CASE WHEN MESSAGE IS NOT NULL AND LENGTH(TRIM(MESSAGE)) > 0
      AND REGEXP_CONTAINS(MESSAGE, r'(?i)\[banner\]')
      THEN 'Replace [banner] with || marketing_banner ||' END,
    CASE WHEN MESSAGE IS NOT NULL AND LENGTH(TRIM(MESSAGE)) > 0
      AND ARRAY_LENGTH(REGEXP_EXTRACT_ALL(MESSAGE, r'\.\.')) > 0
      THEN 'Double Period' END,
    CASE WHEN MESSAGE IS NOT NULL AND LENGTH(TRIM(MESSAGE)) > 0
      AND ARRAY_LENGTH(REGEXP_EXTRACT_ALL(MESSAGE, r'\s{2,}')) > 0
      THEN 'Extra Space' END
    ] AS ERROR_TYPES),

    -- ================= CONTENT VALIDATION =================
    STRUCT('CONTENT_VALIDATION' AS ERROR_COLUMN, [

    -- ✅ Strong swap detection (independent block)
    CASE
    WHEN TITLE IS NOT NULL 
    AND MESSAGE IS NOT NULL
    AND LENGTH(TRIM(TITLE)) > LENGTH(TRIM(MESSAGE))
    THEN CONCAT(
      'Swap likely: TITLE (',
      CAST(LENGTH(TRIM(TITLE)) AS STRING),
      ') > MESSAGE (',
      CAST(LENGTH(TRIM(MESSAGE)) AS STRING),
      ')'
    )
    END,

    -- ✅ Backup: TITLE too long
    CASE
    WHEN TITLE IS NOT NULL 
    AND LENGTH(TRIM(TITLE)) > 50
    THEN CONCAT(
      'TITLE unusually long (',
      CAST(LENGTH(TRIM(TITLE)) AS STRING),
      ')'
    )
    END,

    -- ✅ Backup: MESSAGE too short
    CASE
    WHEN MESSAGE IS NOT NULL 
    AND LENGTH(TRIM(MESSAGE)) < 35
    THEN CONCAT(
      'MESSAGE unusually short (',
      CAST(LENGTH(TRIM(MESSAGE)) AS STRING),
      ')'
    )
    END

    ] AS ERROR_TYPES),


  -- ================= MEDIA_URL =================
  STRUCT('MEDIA_URL' AS ERROR_COLUMN, [
    CASE WHEN MEDIA_URL IS NOT NULL AND LENGTH(TRIM(MEDIA_URL)) > 0
      AND ARRAY_LENGTH(REGEXP_EXTRACT_ALL(MEDIA_URL, r'\.\.')) > 0
      THEN 'Double Period' END,
    CASE WHEN MEDIA_URL IS NOT NULL AND LENGTH(TRIM(MEDIA_URL)) > 0
      AND NOT REGEXP_CONTAINS(MEDIA_URL, r'https://')
      THEN 'https:// prefix' END,
    CASE WHEN MEDIA_URL IS NOT NULL AND LENGTH(TRIM(MEDIA_URL)) > 0
      AND ARRAY_LENGTH(REGEXP_EXTRACT_ALL(MEDIA_URL, r'\s')) > 0
      THEN 'Unexpected Space' END
  ] AS ERROR_TYPES),

  -- ================= PUSHSECTION =================
  STRUCT('PUSHSECTION' AS ERROR_COLUMN, [
    -- Keep only the spacing check
    CASE
      WHEN PUSHSECTION IS NOT NULL
      AND LENGTH(TRIM(PUSHSECTION)) > 0
      AND ARRAY_LENGTH(REGEXP_EXTRACT_ALL(PUSHSECTION, r'\s')) > 0
      THEN 'Unexpected Space'
    END,

    -- NEW RULE: If Pushsection is present there must NOT be an offer type
    CASE
      WHEN COALESCE(TRIM(PUSHSECTION), '') <> ''
      AND COALESCE(OFFER_TYPE_01, '') <> ''
      THEN 'When PUSHSECTION is present, OFFER_TYPE_01 must be empty string'
    END,

    -- NEW RULE: If Pushsection is present there must NOT be an offer id
    CASE
      WHEN COALESCE(TRIM(PUSHSECTION), '') <> ''
      AND OFFER_ID_01 IS NOT NULL
      THEN 'When PUSHSECTION is present, OFFER_ID_01 must be NULL'
    END,

    -- NEW: When there is NO offer (OFFER_ID_01 is NULL), PUSHSECTION must NOT be blank
      CASE
        WHEN OFFER_ID_01 IS NULL
        AND COALESCE(TRIM(PUSHSECTION), '') = ''
        THEN 'When OFFER_ID_01 is NULL, PUSHSECTION must be present (non-blank)'
      END,

    -- NEW: When there is an offer (OFFER_ID_01 is NOT NULL), PUSHSECTION must be blank
      CASE
        WHEN OFFER_ID_01 IS NOT NULL
        AND COALESCE(TRIM(PUSHSECTION), '') <> ''
        THEN 'When OFFER_ID_01 is NOT NULL, PUSHSECTION must be blank'
      END

  ] AS ERROR_TYPES),


  -- ================= SCREENTITLE =================
  STRUCT('SCREENTITLE' AS ERROR_COLUMN, [
    CASE WHEN SCREENTITLE IS NOT NULL AND LENGTH(TRIM(SCREENTITLE)) > 0
      AND ARRAY_LENGTH(REGEXP_EXTRACT_ALL(SCREENTITLE, r'\s')) > 0
      THEN 'Unexpected Space' END
  ] AS ERROR_TYPES),

  -- ================= SUBTITLE =================
  STRUCT('SUBTITLE' AS ERROR_COLUMN, [
    CASE WHEN SUBTITLE IS NOT NULL AND LENGTH(TRIM(SUBTITLE)) > 0
      AND ARRAY_LENGTH(REGEXP_EXTRACT_ALL(SUBTITLE, r'\s{2,}')) > 0
      THEN 'Extra Space' END,
    CASE WHEN SUBTITLE IS NOT NULL AND LENGTH(TRIM(SUBTITLE)) > 0
      AND ARRAY_LENGTH(REGEXP_EXTRACT_ALL(SUBTITLE, r'\.\.')) > 0
      THEN 'Double Period' END
  ] AS ERROR_TYPES),

  -- ================= THEME (PUSH-specific) =================
  STRUCT('THEME' AS ERROR_COLUMN, [
    CASE
      WHEN COALESCE(TRIM(a.THEME), '') = ''
      THEN 'THEME is blank (NULL or whitespace only)'
    END,

    CASE
      WHEN a.THEME IS NOT NULL
           AND LENGTH(TRIM(a.THEME)) > 0
           AND ARRAY_LENGTH(REGEXP_EXTRACT_ALL(a.THEME, r'\s')) > 0
      THEN 'Unexpected Space'
    END,

    CASE
      WHEN NOT REGEXP_CONTAINS(
        a.THEME,
        r'^[^_]+_[^_]+_[^_]+_[^_]+_\d{4}-\d{2}-\d{2}$'
      )
      THEN 'Theme Pattern'
    END,

    CASE
      WHEN SAFE_CAST(
             REGEXP_EXTRACT(a.THEME, r'(\d{4}-\d{2}-\d{2})$')
             AS DATE
           ) IS NULL
      THEN 'Invalid Theme Date'
    END
] AS ERROR_TYPES)
]) AS error,
UNNEST(error.ERROR_TYPES) AS error_type
WHERE a.send_date = start_date
  AND error_type IS NOT NULL
GROUP BY SEND_DATE, PRIORITY, a.THEME, error.ERROR_COLUMN
ORDER BY SEND_DATE, PRIORITY, a.THEME, error.ERROR_COLUMN;


-- DELETE current day data prior to upload
DELETE FROM {{ tables.push_allocation_final_archive }} WHERE SEND_DATE = start_date;

--Insert Final Data IN ARCHIVE
INSERT INTO {{ tables.push_allocation_final_archive }}
  SELECT * FROM
  (SELECT * FROM {{ tables.push_allocation_final }}
  WHERE SEND_DATE = start_date)
  WHERE (THEME,SEND_DATE) NOT IN
  (SELECT AS STRUCT THEME,SEND_DATE
  FROM {{ tables.push_allocation_final_archive }}
  GROUP BY all)
;
