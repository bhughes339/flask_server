CREATE DATABASE IF NOT EXISTS `twitter` DEFAULT CHARACTER SET utf8mb4;
USE `twitter`;

CREATE TABLE IF NOT EXISTS `favorites` (
  `id` varchar(50) NOT NULL,
  `user_id` varchar(50) NOT NULL,
  `text` varchar(1000) DEFAULT NULL,
  `timestamp` datetime NOT NULL,
  `favs` int(11) NOT NULL,
  `retweets` int(11) NOT NULL,
  `is_deleted` tinyint(1) NOT NULL DEFAULT '0',
  `delete_reason` varchar(512) DEFAULT NULL,
  `has_media` tinyint(1) NOT NULL DEFAULT '0',
  `raw_json` mediumtext NOT NULL,
  PRIMARY KEY (`id`)
);
