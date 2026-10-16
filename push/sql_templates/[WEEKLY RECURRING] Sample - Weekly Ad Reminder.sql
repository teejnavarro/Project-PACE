-- Fictional sample template. {{ placeholders }} are filled from the row form at export time.

INSERT INTO {{ tables.push_allocation }}
SELECT a.*
FROM (SELECT DISTINCT
 cast(a.division_id as numeric)
,a.store_banner
,CAST(a.store_id as string)
,CAST(a.household_id as numeric) AS HHID
,a.OS_CUST_ID
,Push_Campaign_Code AS PUSHCAMPAIGN
,'{{ title }}' AS title
,'{{ message }}' AS message
,'' AS media_url
,'' AS media_type
,'' AS pushlinks
,'{{ theme }}' AS theme
,'' AS pushoffertype
,null AS pushofferid
,CAST(start_date as string) AS campaign_id
,'weeklyAd' AS PUSHSECTION
,a.RETAIL_CUSTOMER_UUID AS UUID
,CAST(a.scheduled_time as string)
,'' as param_q
,'' as screentitle
,'' as gameid
,'' as product
,'' as searchterm
,'' as store
,'' as seller
,'' as category
,'' as program
,'' as pagname
,'' as datasource
,'' as modelconfigid
, cast(CURRENT_DATE AS timestamp) as update_dt
,'' as partnerid
,'' as subtitle
,CAST(NULL as BOOL) as autoimage
,'' as eventid
,'' as CANONICALCAMPAIGNID
FROM {{ tables.eligible_push_audience }} a
WHERE a.division_id IN (25,26)
AND a.store_banner IN ('blueharbor','pine_and_peak')
GROUP BY ALL
) a
WHERE HHID NOT IN
  (SELECT HHID
  FROM {{ tables.push_allocation }})
;
