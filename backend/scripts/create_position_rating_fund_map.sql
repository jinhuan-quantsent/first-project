-- ============================================================
-- T2: 建仓评级-板块基金映射表
-- 创建 position_rating_fund_map 表 + 33只基金数据入库
-- 一级行业基金24只(active) + 二级赛道基金9只(reserved)
-- ============================================================

-- 建表
CREATE TABLE IF NOT EXISTS position_rating_fund_map (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sw_sector_code VARCHAR(10) NOT NULL COMMENT '申万一级行业代码(如801050)',
    sw_sector_name VARCHAR(20) NOT NULL COMMENT '申万一级行业名称(如有色金属)',
    fund_code VARCHAR(10) NOT NULL COMMENT '场外C类基金代码(如004433)',
    fund_name VARCHAR(100) NOT NULL COMMENT '基金全称',
    track_index VARCHAR(100) COMMENT '跟踪指数名称',
    fit_degree DECIMAL(5,2) DEFAULT 0 COMMENT '板块贴合度(%)',
    fund_level TINYINT NOT NULL DEFAULT 1 COMMENT '1=一级行业基金, 2=二级赛道基金',
    parent_sector_name VARCHAR(20) COMMENT '二级赛道基金所属的一级行业名称',
    sub_sector_name VARCHAR(50) COMMENT '二级赛道名称(仅level=2时)',
    track_index_code VARCHAR(20) COMMENT '二级赛道对应指数代码(仅level=2时)',
    status VARCHAR(20) NOT NULL DEFAULT 'active' COMMENT 'active=一期启用, reserved=二期预留',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_fund_code (fund_code),
    KEY idx_sw_sector_code (sw_sector_code),
    KEY idx_fund_level_status (fund_level, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='建仓评级-板块基金映射表';

-- ============================================================
-- 一级行业基金（24只，status=active, fund_level=1）
-- ============================================================
INSERT INTO position_rating_fund_map
    (sw_sector_code, sw_sector_name, fund_code, fund_name, track_index, fit_degree, fund_level, status)
VALUES
    ('801050', '有色金属', '004433', '南方有色金属ETF联接C', '中证申万有色金属指数', 100.00, 1, 'active'),
    ('801080', '电子', '012550', '华夏电子ETF联接C', '中证电子指数', 92.00, 1, 'active'),
    ('801710', '建筑材料', '010176', '广发建材ETF联接C', '中证全指建筑材料指数', 90.00, 1, 'active'),
    ('801030', '化工', '012538', '国泰化工ETF联接C', '中证细分化工产业指数', 88.00, 1, 'active'),
    ('801040', '钢铁', '008191', '国泰钢铁ETF联接C', '中证钢铁指数', 90.00, 1, 'active'),
    ('801950', '煤炭', '008280', '国泰中证煤炭ETF联接C', '中证煤炭指数', 85.00, 1, 'active'),
    ('801730', '电力设备', '012697', '华夏新能源ETF联接C', '中证新能源指数', 88.00, 1, 'active'),
    ('801740', '国防军工', '002200', '国泰军工ETF联接C', '中证军工指数', 90.00, 1, 'active'),
    ('801880', '汽车', '013207', '华夏汽车ETF联接C', '中证汽车指数', 87.00, 1, 'active'),
    ('801110', '家用电器', '005065', '国泰家电ETF联接C', '中证全指家用电器指数', 95.00, 1, 'active'),
    ('801150', '医药生物', '007883', '易方达沪深300医药卫生ETF联接C', '沪深300医药卫生指数', 85.00, 1, 'active'),
    ('801180', '房地产', '004643', '南方房地产ETF联接C', '中证全指房地产指数', 95.00, 1, 'active'),
    ('801120', '食品饮料', '013106', '华夏食品饮料ETF联接C', '中证食品饮料指数', 92.00, 1, 'active'),
    ('801770', '通信', '007818', '国泰通信ETF联接C', '中证全指通信设备指数', 90.00, 1, 'active'),
    ('801780', '银行', '007172', '华宝中证银行ETF联接C', '中证银行指数', 95.00, 1, 'active'),
    ('801190', '非银金融', '007882', '易方达沪深300非银ETF联接C', '沪深300非银行金融指数', 90.00, 1, 'active'),
    ('801750', '计算机', '004554', '国泰计算机ETF联接C', '中证计算机指数', 93.00, 1, 'active'),
    ('801760', '传媒', '004753', '广发传媒ETF联接C', '中证传媒指数', 92.00, 1, 'active'),
    ('801160', '公用事业', '016186', '华夏电力ETF联接C', '中证电力指数', 82.00, 1, 'active'),
    ('801960', '环保', '002984', '广发中证环保产业ETF联接C', '中证环保产业指数', 88.00, 1, 'active'),
    ('801010', '农林牧渔', '012721', '华夏农业ETF联接C', '中证农业指数', 85.00, 1, 'active'),
    ('801210', '社会服务', '016831', '华夏旅游ETF联接C', '中证旅游主题指数', 75.00, 1, 'active'),
    ('801890', '机械设备', '013232', '华夏高端装备ETF联接C', '中证高端装备制造指数', 70.00, 1, 'active'),
    ('801720', '建筑装饰', '013277', '华夏基建ETF联接C', '中证基建工程指数', 70.00, 1, 'active');

-- ============================================================
-- 二级赛道基金（9只，status=reserved, fund_level=2）
-- ============================================================
INSERT INTO position_rating_fund_map
    (sw_sector_code, sw_sector_name, fund_code, fund_name, track_index, fit_degree,
     fund_level, parent_sector_name, sub_sector_name, track_index_code, status)
VALUES
    ('801080', '电子', '008888', '华夏国证半导体芯片ETF联接C', '国证半导体芯片指数', 95.00,
     2, '电子', '半导体芯片', '399394', 'reserved'),
    ('801080', '电子', '012863', '国泰中证消费电子主题ETF联接C', '中证消费电子主题指数', 90.00,
     2, '电子', '消费电子', '931494', 'reserved'),
    ('801730', '电力设备', '011680', '华泰柏瑞中证光伏产业ETF联接C', '中证光伏产业指数', 95.00,
     2, '电力设备', '光伏产业', '931151', 'reserved'),
    ('801730', '电力设备', '016038', '华夏中证储能产业ETF联接C', '中证储能产业指数', 92.00,
     2, '电力设备', '储能产业', '931746', 'reserved'),
    ('801730', '电力设备', '012862', '国泰中证锂电池ETF联接C', '中证锂电池指数', 93.00,
     2, '电力设备', '锂电池', '931719', 'reserved'),
    ('801150', '医药生物', '010372', '汇添富中证创新药产业ETF联接C', '中证创新药产业指数', 95.00,
     2, '医药生物', '创新药产业', '931152', 'reserved'),
    ('801150', '医药生物', '015296', '国泰中证医疗器械ETF联接C', '中证医疗器械指数', 94.00,
     2, '医药生物', '医疗器械', '931367', 'reserved'),
    ('801050', '有色金属', '011036', '华夏中证稀土产业ETF联接C', '中证稀土产业指数', 95.00,
     2, '有色金属', '稀土产业', '930597', 'reserved'),
    ('801740', '国防军工', '015560', '国泰中证军工电子ETF联接C', '中证军工电子指数', 92.00,
     2, '国防军工', '军工电子', '931065', 'reserved');

-- ============================================================
-- 验证查询
-- ============================================================
-- 总记录数
SELECT COUNT(*) AS total_count FROM position_rating_fund_map;
-- active 记录数
SELECT COUNT(*) AS active_count FROM position_rating_fund_map WHERE status = 'active';
-- reserved 记录数
SELECT COUNT(*) AS reserved_count FROM position_rating_fund_map WHERE status = 'reserved';
-- fund_level=1 记录数
SELECT COUNT(*) AS level1_count FROM position_rating_fund_map WHERE fund_level = 1;
-- fund_level=2 记录数
SELECT COUNT(*) AS level2_count FROM position_rating_fund_map WHERE fund_level = 2;
