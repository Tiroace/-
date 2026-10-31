-- MySQL 首次初始化脚本（容器首次创建数据卷时自动执行一次）
--
-- 挂载方式：docker-compose.yml 把本目录挂到容器的
--   /docker-entrypoint-initdb.d
-- 官方镜像会在数据目录为空时按文件名顺序执行其中的 .sql/.sh。
--
-- ⚠️ 只在**首次初始化**（mysql_data 卷为空）时生效；
--    已经初始化过的库，改这里不会重跑，变更要走迁移脚本。

-- 统一时区与字符集口径（和 compose 的 command 参数一致，这里是兜底）
SET GLOBAL time_zone = '+08:00';

-- 业务库由 MYSQL_DATABASE 环境变量创建，这里不重复建库。
-- 后续表结构迁移脚本放本目录，命名 10-xxx.sql、20-xxx.sql（按序号执行）。
