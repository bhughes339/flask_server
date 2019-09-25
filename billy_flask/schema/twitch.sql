CREATE DATABASE IF NOT EXISTS `twitch` DEFAULT CHARACTER SET utf8mb4;
USE `twitch`;

CREATE TABLE IF NOT EXISTS `stream` (
  `room` varchar(50) NOT NULL,
  `stream_id` varchar(50) NOT NULL,
  PRIMARY KEY (`room`)
);
