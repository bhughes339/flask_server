CREATE DATABASE IF NOT EXISTS `slack` DEFAULT CHARACTER SET utf8mb4;
USE `slack`;

CREATE TABLE IF NOT EXISTS `channels` (
  `id` varchar(50) NOT NULL,
  `name` varchar(50) NOT NULL,
  PRIMARY KEY (`id`)
);

CREATE TABLE IF NOT EXISTS `pins` (
  `timestamp` varchar(50) NOT NULL,
  `text` varchar(2047) NOT NULL,
  `userid` varchar(9) DEFAULT NULL,
  `channel` varchar(9) NOT NULL,
  `pinnedby` varchar(9) DEFAULT NULL,
  PRIMARY KEY (`timestamp`)
);

CREATE TABLE IF NOT EXISTS `users` (
  `id` varchar(9) NOT NULL DEFAULT '',
  `name` varchar(50) NOT NULL,
  `avatar` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`)
);
