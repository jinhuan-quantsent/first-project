-- ============================================================
-- T2b: 修正 position_rating_fund_map 表基金代码
-- 日期: 2026-06-25
-- 说明: 经天天基金网+Tushare双重验证，修正16只基金代码/名称，
--       5只无匹配C类联接基金标记为 unavailable
-- ============================================================

-- =============================================
-- 一、一级行业基金 - UPDATE 代码（13只）
-- =============================================

-- 1. 801080 电子: 012550(A类)→012551(C类)
UPDATE position_rating_fund_map SET fund_code='012551', fund_name='华宝中证电子50ETF联接C', track_index='中证电子50指数', fit_degree=90.00 WHERE sw_sector_code='801080' AND fund_level=1;

-- 2. 801710 建筑材料: 010176(不存在)→004857
UPDATE position_rating_fund_map SET fund_code='004857', fund_name='广发中证全指建筑材料指数C', track_index='中证全指建筑材料指数', fit_degree=88.00 WHERE sw_sector_code='801710' AND fund_level=1;

-- 3. 801040 钢铁: 008191(货币基金)→008190
UPDATE position_rating_fund_map SET fund_code='008190', fund_name='国泰中证钢铁ETF联接C', track_index='中证钢铁指数', fit_degree=90.00 WHERE sw_sector_code='801040' AND fund_level=1;

-- 4. 801730 电力设备: 012697(不存在)→019316(易方达,开放申购)
UPDATE position_rating_fund_map SET fund_code='019316', fund_name='易方达中证新能源ETF联接发起式C', track_index='中证新能源指数', fit_degree=88.00 WHERE sw_sector_code='801730' AND fund_level=1;

-- 5. 801740 国防军工: 002200(货币基金)→015599(LOF C类)
UPDATE position_rating_fund_map SET fund_code='015599', fund_name='国泰国证航天军工指数(LOF)C', track_index='国证航天军工指数', fit_degree=85.00 WHERE sw_sector_code='801740' AND fund_level=1;

-- 6. 801880 汽车: 013207(短债基金)→022387
UPDATE position_rating_fund_map SET fund_code='022387', fund_name='华夏中证汽车零部件主题ETF发起式联接C', track_index='中证汽车零部件主题指数', fit_degree=80.00 WHERE sw_sector_code='801880' AND fund_level=1;

-- 7. 801110 家用电器: 005065(货币基金)→008714
UPDATE position_rating_fund_map SET fund_code='008714', fund_name='国泰中证全指家用电器ETF联接C', track_index='中证全指家用电器指数', fit_degree=95.00 WHERE sw_sector_code='801110' AND fund_level=1;

-- 8. 801120 食品饮料: 013106(光伏基金)→013126
UPDATE position_rating_fund_map SET fund_code='013126', fund_name='华夏中证细分食品饮料产业主题ETF联接C', track_index='中证细分食品饮料产业主题指数', fit_degree=92.00 WHERE sw_sector_code='801120' AND fund_level=1;

-- 9. 801780 银行: 007172(债券基金)→006697
UPDATE position_rating_fund_map SET fund_code='006697', fund_name='华宝中证银行ETF联接C', track_index='中证银行指数', fit_degree=95.00 WHERE sw_sector_code='801780' AND fund_level=1;

-- 10. 801750 计算机: 004554(货币基金)→010210
UPDATE position_rating_fund_map SET fund_code='010210', fund_name='国泰中证计算机主题ETF联接C', track_index='中证计算机主题指数', fit_degree=93.00 WHERE sw_sector_code='801750' AND fund_level=1;

-- 11. 801010 农林牧渔: 012721(养老基金)→016078
UPDATE position_rating_fund_map SET fund_code='016078', fund_name='华夏中证农业主题ETF发起联接C', track_index='中证农业主题指数', fit_degree=85.00 WHERE sw_sector_code='801010' AND fund_level=1;

-- 12. 801890 机械设备: 013232(债券基金)→021201
UPDATE position_rating_fund_map SET fund_code='021201', fund_name='华夏中证装备产业ETF发起式联接C', track_index='中证装备产业指数', fit_degree=75.00 WHERE sw_sector_code='801890' AND fund_level=1;

-- 13. 801720 建筑装饰: 013277(创业板ETF)→017684
UPDATE position_rating_fund_map SET fund_code='017684', fund_name='华夏中证基建ETF发起式联接C', track_index='中证基建指数', fit_degree=80.00 WHERE sw_sector_code='801720' AND fund_level=1;

-- =============================================
-- 二、一级行业基金 - UPDATE 基金名称（3只，代码正确但名称/管理人有误）
-- =============================================

-- 14. 801030 化工: 代码012538正确,但管理人是华宝非国泰
UPDATE position_rating_fund_map SET fund_name='华宝中证细分化工产业主题ETF联接C', track_index='中证细分化工产业主题指数', fit_degree=88.00 WHERE fund_code='012538';

-- 15. 801160 公用事业: 代码016186正确,但管理人是广发非华夏
UPDATE position_rating_fund_map SET fund_name='广发中证全指电力公用事业ETF联接C', track_index='中证全指电力公用事业指数', fit_degree=82.00 WHERE fund_code='016186';

-- 16. 稀土(二级): 代码011036正确,但管理人是嘉实非华夏
UPDATE position_rating_fund_map SET fund_name='嘉实中证稀土产业ETF联接C', track_index='中证稀土产业指数', fit_degree=95.00 WHERE fund_code='011036';

-- =============================================
-- 三、二级赛道基金 - UPDATE 代码（3只）
-- =============================================

-- 17. 消费电子: 012863(电池基金)→014907
UPDATE position_rating_fund_map SET fund_code='014907', fund_name='国泰中证消费电子主题ETF联接C', track_index='中证消费电子主题指数', fit_degree=90.00 WHERE sub_sector_name='消费电子' AND fund_level=2;

-- 18. 光伏产业: 011680(混合基金)→012680
UPDATE position_rating_fund_map SET fund_code='012680', fund_name='华泰柏瑞中证光伏产业ETF联接C', track_index='中证光伏产业指数', fit_degree=95.00 WHERE sub_sector_name='光伏产业' AND fund_level=2;

-- 19. 医疗器械: 015296(混合基金)→021251
UPDATE position_rating_fund_map SET fund_code='021251', fund_name='华夏中证全指医疗器械ETF发起式联接C', track_index='中证全指医疗器械指数', fit_degree=94.00 WHERE sub_sector_name='医疗器械' AND fund_level=2;

-- =============================================
-- 四、标记为 unavailable（5只，无匹配C类联接基金）
-- =============================================

-- 20. 801210 社会服务(旅游): 无OTC C类联接基金
UPDATE position_rating_fund_map SET status='unavailable' WHERE sw_sector_code='801210' AND fund_level=1;

-- 21. 储能产业: 无匹配
UPDATE position_rating_fund_map SET status='unavailable' WHERE sub_sector_name='储能产业' AND fund_level=2;

-- 22. 锂电池: 无匹配
UPDATE position_rating_fund_map SET status='unavailable' WHERE sub_sector_name='锂电池' AND fund_level=2;

-- 23. 创新药产业: 无匹配
UPDATE position_rating_fund_map SET status='unavailable' WHERE sub_sector_name='创新药产业' AND fund_level=2;

-- 24. 军工电子: 无匹配
UPDATE position_rating_fund_map SET status='unavailable' WHERE sub_sector_name='军工电子' AND fund_level=2;
