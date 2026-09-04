#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试按周查询的日期区间生成"""

from datetime import date
from extraction_service import generate_date_ranges, generate_weekly_ranges


def test_comparison():
    """对比滚动窗口与按周查询的区间数量"""
    
    # 测试最近30天
    print("="*60)
    print("测试场景：最近 30 天")
    print("="*60)
    
    # 原始方式：7天滚动窗口
    rolling_ranges = generate_date_ranges(days_back=30, range_days=7)
    print(f"\n原始方式（7天滚动窗口）：")
    print(f"  区间数量: {len(rolling_ranges)}")
    print(f"  查询次数: {len(rolling_ranges) * 3} (× 3个参数)")
    print(f"  前3个区间示例:")
    for i, (start, end) in enumerate(rolling_ranges[:3]):
        print(f"    {i+1}. {start} 至 {end}")
    print(f"  ...")
    
    # 新方式：按自然周
    weekly_ranges = generate_weekly_ranges(days_back=30)
    print(f"\n新方式（按自然周）：")
    print(f"  区间数量: {len(weekly_ranges)}")
    print(f"  查询次数: {len(weekly_ranges) * 3} (× 3个参数)")
    print(f"  完整区间:")
    for i, (start, end) in enumerate(weekly_ranges):
        # 解析日期并显示星期
        from datetime import datetime
        start_date = datetime.strptime(start, '%Y-%m-%d')
        end_date = datetime.strptime(end, '%Y-%m-%d')
        weekdays_cn = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
        print(f"    {i+1}. {start} ({weekdays_cn[start_date.weekday()]}) "
              f"至 {end} ({weekdays_cn[end_date.weekday()]})")
    
    print(f"\n查询次数对比：")
    print(f"  原始方式: {len(rolling_ranges) * 3} 次")
    print(f"  按周方式: {len(weekly_ranges) * 3} 次")
    print(f"  减少: {(len(rolling_ranges) - len(weekly_ranges)) * 3} 次 "
          f"({(1 - len(weekly_ranges)/len(rolling_ranges)) * 100:.1f}%)")
    
    # 测试指定日期区间
    print("\n" + "="*60)
    print("测试场景：2026-04-01 到 2026-04-30 (整月)")
    print("="*60)
    
    rolling_ranges_month = generate_date_ranges(days_back=29, range_days=7, 
                                                end_date='2026-04-30')
    weekly_ranges_month = generate_weekly_ranges(days_back=29, end_date='2026-04-30')
    
    print(f"\n原始方式: {len(rolling_ranges_month)} 个区间 × 3 = {len(rolling_ranges_month) * 3} 次查询")
    print(f"按周方式: {len(weekly_ranges_month)} 个区间 × 3 = {len(weekly_ranges_month) * 3} 次查询")
    print(f"\n按周区间详情:")
    for i, (start, end) in enumerate(weekly_ranges_month):
        from datetime import datetime
        start_date = datetime.strptime(start, '%Y-%m-%d')
        end_date = datetime.strptime(end, '%Y-%m-%d')
        weekdays_cn = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
        days = (end_date - start_date).days + 1
        print(f"  {i+1}. {start} 至 {end} ({days}天)")


if __name__ == '__main__':
    test_comparison()
