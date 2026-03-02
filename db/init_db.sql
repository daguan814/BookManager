CREATE DATABASE IF NOT EXISTS `bookmanager`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE `bookmanager`;

CREATE TABLE IF NOT EXISTS `books` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `isbn` VARCHAR(20) NOT NULL,
  `title` VARCHAR(255) NOT NULL,
  `author` VARCHAR(255) NULL,
  `publisher` VARCHAR(255) NULL,
  `pubdate` VARCHAR(20) NULL,
  `gist` TEXT NULL,
  `price` VARCHAR(50) NULL,
  `page` VARCHAR(50) NULL,
  `publish_year` VARCHAR(20) NULL,
  `cover_url` VARCHAR(500) NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_books_isbn` (`isbn`),
  KEY `idx_books_isbn` (`isbn`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `inventory` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `book_id` INT NOT NULL,
  `quantity` INT NOT NULL DEFAULT 0,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_inventory_book_id` (`book_id`),
  KEY `idx_inventory_book_id` (`book_id`),
  CONSTRAINT `fk_inventory_book_id` FOREIGN KEY (`book_id`) REFERENCES `books` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `inventory_logs` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `book_id` INT NOT NULL,
  `action` VARCHAR(10) NOT NULL,
  `quantity` INT NOT NULL,
  `related_log_id` INT NULL,
  `operator_name` VARCHAR(100) NULL,
  `borrower_name` VARCHAR(100) NULL,
  `borrower_class` VARCHAR(100) NULL,
  `remark` TEXT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_logs_book_id` (`book_id`),
  KEY `idx_logs_related_log_id` (`related_log_id`),
  KEY `idx_logs_created_at` (`created_at`),
  CONSTRAINT `fk_logs_book_id` FOREIGN KEY (`book_id`) REFERENCES `books` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
