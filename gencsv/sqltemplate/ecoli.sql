select 		
	sa.sampno,	
	sa.loccode,	
	sa.locdescr,	
	sa.current_state,	
	sa.coldate,	
	-- 优先使用 bic_bl_aec_district（标准 18 区名），不存在时退回 district（邻里名）
	coalesce(nullif(trim(suf.bic_bl_aec_district), ''), lower(suf.district)) as district,
	suf.loc_gps_latitude,	
	suf.loc_gps_longitude,	
	re.result,	
	re.rawresult,	
	case	
		when suf.loc_gps_latitude is null or suf.loc_gps_latitude = ''
		then null
		else try_cast(suf.loc_gps_latitude as float)
	end as loc_gps_latitude_value,	
	case	
		when suf.loc_gps_longitude is null or suf.loc_gps_longitude = ''
		then null
		else try_cast(suf.loc_gps_longitude as float)
	end as loc_gps_longitude_value	
	,re.acode 	
		
--	try_cast(re.rawresult as float) as raw_result_value	
from		
	sample as sa	
left join suserflds as suf		
		on
	sa.sampno = suf.sampno	
inner join result as re		
		on
	sa.sampno = re.sampno	
where		
	1 = 1	
	and re.acode = 'ECOLI'	
	AND coldate>=[date_from]	
	AND coldate<=[date_to]	
	and sa.current_state in ('SAMP_VALIDATED','SAMP_REPORT_QUEUE')	
	and re.result is not null	
	and re.result <> ''	
	and try_cast(re.result as float) is not null	
	and re.rawresult is not null	
	and re.rawresult <> ''	
	and try_cast(re.rawresult as float) is not null	
	and loccode LIKE 'SR-%'
  	and CHARINDEX('-FC-', loccode) > 0
	order by coldate, district desc	

