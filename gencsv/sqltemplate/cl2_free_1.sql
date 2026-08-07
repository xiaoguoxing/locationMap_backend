-- Chlorine Free 1 Query
-- Parameters: [date_from], [date_to]
-- Returns: Sample data with results for the specified date range

select TOP 1000		
	sa.sampno,	
	sa.loccode,	
	sa.locdescr,	
	sa.current_state,	
	sa.coldate,	
	sa.owner,	
	lower(suf.district) as district,	
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
	AND re.acode = 'CL2_FREE_1'	
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
	order by cast(coldate as date),owner 	

