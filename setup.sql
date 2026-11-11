CREATE DATABASE IF NOT EXISTS raze
    CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE raze;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS games (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(120) NOT NULL UNIQUE,
    genre VARCHAR(40) NOT NULL,
    price DECIMAL(10, 2) NOT NULL CHECK (price >= 0),
    developer VARCHAR(100) NOT NULL,
    platform VARCHAR(80) NOT NULL,
    is_available BOOLEAN NOT NULL DEFAULT TRUE
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS orders (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    purchased_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS order_items (
    game_id INT UNSIGNED PRIMARY KEY,
    order_id INT UNSIGNED NOT NULL,
    price_paid DECIMAL(10, 2) NOT NULL CHECK (price_paid >= 0),
    FOREIGN KEY (game_id) REFERENCES games(id),
    FOREIGN KEY (order_id) REFERENCES orders(id)
) ENGINE = InnoDB;

-- Catalogue seed
-- Stable IDs preserve catalogue edits when setup is rerun on a fresh installation.
-- Prices are illustrative INR. Platform identifies the version offered by RAZE.
INSERT INTO games (id, title, genre, price, developer, platform) VALUES
    (4, 'Red Dead Redemption 2', 'Action-Adventure', 3199.00, 'Rockstar Games', 'Windows'),
    (3, 'Cyberpunk 2077', 'RPG', 2999.00, 'CD Projekt Red', 'Windows'),
    (2, 'Grand Theft Auto V', 'Action-Adventure', 2499.00, 'Rockstar North', 'Windows'),
    (17, 'The Witcher 3: Wild Hunt', 'RPG', 1499.00, 'CD Projekt Red', 'Windows'),
    (25, 'Ghost of Tsushima Director''s Cut', 'Action-Adventure', 3999.00, 'Sucker Punch Productions / Nixxes Software', 'Windows'),
    (26, 'Ghost of Yōtei', 'Action-Adventure', 4999.00, 'Sucker Punch Productions', 'PS5'),
    (27, 'God of War Ragnarök', 'Action-Adventure', 3999.00, 'Santa Monica Studio / Jetpack Interactive', 'Windows'),
    (13, 'Forza Horizon 5', 'Racing', 3499.00, 'Playground Games', 'Windows'),
    (22, 'Subnautica', 'Survival', 999.00, 'Unknown Worlds Entertainment', 'Windows'),
    (28, 'Days Gone', 'Action-Adventure', 2499.00, 'Bend Studio', 'Windows'),
    (29, 'Detroit: Become Human', 'Narrative Adventure', 1799.00, 'Quantic Dream', 'Windows'),
    (30, 'The Last of Us Part I', 'Action-Adventure', 3999.00, 'Naughty Dog / Iron Galaxy Studios', 'Windows'),
    (31, 'Max Payne', 'Shooter', 349.00, 'Remedy Entertainment', 'Windows'),
    (32, 'Mafia: Definitive Edition', 'Action-Adventure', 1999.00, 'Hangar 13', 'Windows'),
    (33, 'Sleeping Dogs: Definitive Edition', 'Action-Adventure', 999.00, 'United Front Games', 'Windows'),
    (34, 'Uncharted: Legacy of Thieves Collection', 'Action-Adventure', 3299.00, 'Naughty Dog / Iron Galaxy Studios', 'Windows'),
    (35, 'Alan Wake 2', 'Survival Horror', 3299.00, 'Remedy Entertainment', 'Windows'),
    (36, 'Resident Evil 4 Remake', 'Survival Horror', 2999.00, 'Capcom', 'Windows'),
    (37, 'Counter-Strike 2', 'Shooter', 0.00, 'Valve', 'Windows'),
    (38, 'Life is Strange', 'Narrative Adventure', 799.00, 'Dontnod Entertainment', 'Windows'),
    (5, 'Elden Ring', 'RPG', 3599.00, 'FromSoftware', 'Windows'),
    (39, 'Sekiro: Shadows Die Twice', 'Action-Adventure', 3299.00, 'FromSoftware', 'Windows'),
    (40, 'Dark Souls III', 'RPG', 2999.00, 'FromSoftware', 'Windows'),
    (41, 'Lies of P', 'RPG', 2999.00, 'NEOWIZ / Round8 Studio', 'Windows'),
    (42, 'Black Myth: Wukong', 'RPG', 3599.00, 'Game Science', 'Windows'),
    (7, 'Hollow Knight', 'Metroidvania', 599.00, 'Team Cherry', 'Windows'),
    (43, 'Schedule I', 'Simulation', 899.00, 'TVGS', 'Windows'),
    (44, 'Lethal Company', 'Survival Horror', 499.00, 'Zeekerss', 'Windows'),
    (45, 'Phasmophobia', 'Survival Horror', 899.00, 'Kinetic Games', 'Windows'),
    (46, 'Fears to Fathom', 'Horror', 499.00, 'Rayll', 'Windows'),
    (47, 'Pacify', 'Horror', 299.00, 'Shawn Hitchcock', 'Windows'),
    (48, 'Getting Over It with Bennett Foddy', 'Platformer', 349.00, 'Bennett Foddy', 'Windows')
ON DUPLICATE KEY UPDATE id = games.id;
