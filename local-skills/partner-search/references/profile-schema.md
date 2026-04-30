# Profile Schema

Use this schema for MySQL columns.

## Recommended Fields

| Field | Meaning |
| --- | --- |
| `id` | Stable profile id |
| `name` | Display name |
| `avatar_url` | Profile avatar URL summary |
| `photo_count` | Number of gallery photos summary, excluding the avatar |
| `gender` | `男` / `女` or equivalent |
| `age` | Integer age |
| `city` | Current city |
| `district` | Current district or usual activity area |
| `hometown` | Hometown or family origin |
| `settlement_city` | Intended long-term settlement city |
| `housing_status` | Housing situation |
| `car_status` | Car ownership status |
| `height` | Height in cm |
| `education` | Education level |
| `job` | Job or role |
| `income_range` | Income band or rough range |
| `relationship_goal` | `认真恋爱`, `结婚导向`, `先接触看看` |
| `preferred_age_min` / `preferred_age_max` | Preferred partner age range |
| `preferred_cities` | Preferred partner cities |
| `preferred_height_min` / `preferred_height_max` | Preferred partner height range |
| `preferred_education_min` | Minimum preferred partner education |
| `preferred_income_min_wan` / `preferred_income_max_wan` | Preferred partner income range in `万/年` |
| `personality` | Personality traits |
| `values` | Values, spending style, family outlook |
| `lifestyle` | Routine, exercise, smoking, drinking, pets |
| `hobbies` | Hobbies and interests |
| `life_routine` | Structured routine summary such as regular, stable, or busy-but-coordinatable |
| `communication_style` | Structured communication style such as proactive, rational-direct, or slow-warm |
| `dating_pace` | Structured dating pace such as natural, slow-warm, or serious-progress |
| `expression_style` | Structured self-expression and life-feel summary |
| `relationship_capacity` | Structured relationship bandwidth / investment signal |
| `interaction_comfort` | Whether the person feels easygoing, low-pressure, or needs more磨合 in interaction |
| `patience_level` | Structured patience signal such as high, stable, or pace-fast |
| `life_texture` | Whether the profile feels plain-stable, has生活感, or has见识+生活感 |
| `career_intensity` | Structured work-rhythm summary such as busy-but-coordinatable or regular-stable |
| `exercise_habit` | Structured exercise habit such as regular, light, or not obvious |
| `growth_signal` | Structured career momentum such as rising, mature-platform, or stable |
| `warmth_style` | Structured chat warmth such as warm-responsive, rational-not-cold, or restrained |
| `aesthetic_expression` | Structured aesthetic / expressive signal such as clear taste output or plain |
| `conversation_resonance` | Whether the person can聊想法也聊日常, can接情绪, or mainly stays at practical info exchange |
| `personal_presence` | Whether the profile feels memorable, warm-and-enduring, or conditionally correct but flat |
| `lightness_humor` | Whether the person feels playful / not wooden in chat, or more steady and restrained |
| `consumption_attitude` | Structured spending stance such as clear-headed and practical, selective but knows how to live, or everyday-home-oriented |
| `chat_texture` | Whether chat feels lively-with-substance, easy-to-follow, steady-smooth, or mostly functional |
| `commitment_clarity` | Whether the person is explicitly entering with long-term intent or still more “先聊熟再说” |
| `relationship_execution` | Whether the person can turn long-term intent into concrete pacing, expectations, and plans |
| `blended_family_readiness` | Whether the profile has concretely thought through divorced-with-children reality |
| `smoking` | `否`, `是`, `偶尔`, `未知` |
| `drinking` | `否`, `是`, `偶尔`, `未知` |
| `long_distance` | `接受`, `不接受`, `可协商`, `未知` |
| `accept_long_distance` | Whether the profile accepts long-distance matches |
| `accept_smoking` / `accept_drinking` | Whether the profile accepts those habits in a partner |
| `accept_marital_status` | Acceptable partner marital statuses |
| `accept_marital_status_strength` | Whether accepting divorce history is explicit, cautious, or surface-level |
| `marital_status` | Single, divorced, etc. |
| `has_children` / `children_count` | Whether the profile has children and how many |
| `children_living_with_self` | Whether the children live with the profile |
| `want_children` | Future child plan |
| `accept_partner_children` | Whether the profile accepts a partner who already has children |
| `accept_partner_children_strength` | Whether accepting a partner with children is explicit, cautious, or surface-level |
| `marriage_timeline` | Marriage timing expectation |
| `family_background` | Short family note |
| `notes` | Free-text notes |
| `profile_status` | Whether the profile is active, paused, matched, or archived |
| `last_active_at` | Last active timestamp |
| `verified_level` | Verification level |
| `source_channel` | Where the profile came from |
| `created_at` / `updated_at` | Record creation and update timestamps |

## MySQL Table Example

Use `utf8mb4` and keep one row per profile. Store only summary image fields in `profiles`; use `profile_photos` as the canonical album source.

```sql
CREATE TABLE profiles (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(64),
  avatar_url VARCHAR(255),
  photo_count TINYINT UNSIGNED,
  gender VARCHAR(8),
  age INT,
  city VARCHAR(64),
  district VARCHAR(64),
  hometown VARCHAR(64),
  settlement_city VARCHAR(64),
  housing_status ENUM('已购房','租房','与家人同住','无房','可协商','未知'),
  car_status ENUM('有车','无车','计划购车','可协商','未知'),
  height INT,
  education VARCHAR(32),
  job VARCHAR(64),
  income_range VARCHAR(32),
  relationship_goal VARCHAR(32),
  preferred_age_min TINYINT UNSIGNED,
  preferred_age_max TINYINT UNSIGNED,
  preferred_cities TEXT,
  preferred_height_min SMALLINT UNSIGNED,
  preferred_height_max SMALLINT UNSIGNED,
  preferred_education_min VARCHAR(32),
  preferred_income_min_wan SMALLINT UNSIGNED,
  preferred_income_max_wan SMALLINT UNSIGNED,
  personality TEXT,
  values TEXT,
  lifestyle TEXT,
  hobbies TEXT,
  life_routine VARCHAR(32),
  communication_style VARCHAR(32),
  dating_pace VARCHAR(32),
  expression_style VARCHAR(32),
  relationship_capacity VARCHAR(32),
  interaction_comfort VARCHAR(32),
  patience_level VARCHAR(32),
  life_texture VARCHAR(32),
  career_intensity VARCHAR(32),
  exercise_habit VARCHAR(32),
  growth_signal VARCHAR(32),
  warmth_style VARCHAR(32),
  aesthetic_expression VARCHAR(32),
  conversation_resonance VARCHAR(32),
  personal_presence VARCHAR(32),
  lightness_humor VARCHAR(32),
  consumption_attitude VARCHAR(32),
  chat_texture VARCHAR(32),
  commitment_clarity VARCHAR(32),
  relationship_execution VARCHAR(32),
  blended_family_readiness VARCHAR(32),
  smoking VARCHAR(16),
  drinking VARCHAR(16),
  long_distance VARCHAR(16),
  accept_long_distance ENUM('接受','不接受','可协商','未知'),
  accept_smoking ENUM('接受','不接受','可协商','未知'),
  accept_drinking ENUM('接受','不接受','可协商','未知'),
  accept_marital_status TEXT,
  accept_marital_status_strength VARCHAR(32),
  marital_status VARCHAR(32),
  has_children TINYINT(1),
  children_count TINYINT UNSIGNED,
  children_living_with_self TINYINT(1),
  want_children ENUM('想要','不要','可协商','未知'),
  accept_partner_children ENUM('接受','不接受','可协商','谨慎可协商','未知'),
  accept_partner_children_strength VARCHAR(32),
  marriage_timeline ENUM('半年内','1年内','2年内','合适就结婚','暂不考虑','未知'),
  family_background TEXT,
  notes TEXT,
  profile_status ENUM('active','paused','matched','archived') NOT NULL DEFAULT 'active',
  last_active_at DATETIME,
  verified_level ENUM('none','basic','photo','id','offline') NOT NULL DEFAULT 'none',
  source_channel VARCHAR(64),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

For a more realistic album model, store individual images in a child table and keep `avatar_url` and `photo_count` in `profiles` as summary fields:

```sql
CREATE TABLE profile_photos (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  profile_id BIGINT NOT NULL,
  photo_url VARCHAR(255) NOT NULL,
  photo_type ENUM('avatar','gallery') NOT NULL DEFAULT 'gallery',
  sort_order TINYINT UNSIGNED NOT NULL DEFAULT 1,
  is_primary TINYINT(1) NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_profile_photos_profile_sort (profile_id, sort_order),
  KEY idx_profile_photos_profile_primary (profile_id, is_primary)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

If your MySQL table uses aliases such as `姓名` or `城市`, the search script normalizes common variants automatically.

## Recommended Indexes

If you expect more than a small profile library, add indexes for the structured filters that the prefilter pushes into MySQL. The exact mix depends on your query patterns, but a reasonable starting point is:

```sql
CREATE INDEX idx_profiles_search_core
  ON profiles (gender, city, district, settlement_city, profile_status, verified_level);

CREATE INDEX idx_profiles_search_age
  ON profiles (age);

CREATE INDEX idx_profiles_search_goal
  ON profiles (relationship_goal);

CREATE INDEX idx_profiles_search_active
  ON profiles (last_active_at);
```

Prefer a case-insensitive collation such as `utf8mb4_unicode_ci` for those structured text columns. The skill's SQL prefilter is optimized for normalized structured values, not for arbitrary free-text cleanup inside the query.

## Supported Chinese Aliases

The script normalizes common aliases automatically.

| Canonical | Accepted aliases |
| --- | --- |
| `name` | `姓名`, `昵称` |
| `gender` | `性别` |
| `age` | `年龄` |
| `city` | `城市`, `所在地`, `现居地` |
| `height` | `身高` |
| `education` | `学历` |
| `job` | `工作`, `职业` |
| `income_range` | `收入`, `收入范围` |
| `relationship_goal` | `目标`, `恋爱目标`, `婚恋目标`, `关系目标` |
| `preferred_age_min` / `preferred_age_max` | `择偶年龄下限`, `择偶年龄上限`, `年龄要求下限`, `年龄要求上限` |
| `preferred_cities` | `择偶城市`, `意向城市`, `期望城市`, `偏好城市` |
| `preferred_height_min` / `preferred_height_max` | `择偶身高下限`, `择偶身高上限`, `身高要求下限`, `身高要求上限` |
| `preferred_education_min` | `择偶学历下限`, `最低学历`, `学历要求` |
| `preferred_income_min_wan` / `preferred_income_max_wan` | `择偶收入下限`, `择偶收入上限`, `最低收入`, `最高收入` |
| `personality` | `性格` |
| `values` | `价值观`, `消费观` |
| `lifestyle` | `生活方式`, `作息` |
| `hobbies` | `兴趣`, `爱好` |
| `consumption_attitude` | `消费观锚点`, `消费观类型`, `花钱观` |
| `chat_texture` | `聊天质感`, `聊天趣味`, `聊天顺滑度` |
| `relationship_execution` | `现实推进方式`, `关系推进方式`, `推进执行感` |
| `smoking` | `抽烟`, `吸烟` |
| `drinking` | `喝酒`, `饮酒` |
| `long_distance` | `异地`, `接受异地` |
| `accept_long_distance` | `是否接受异地`, `可否异地` |
| `accept_smoking` | `接受抽烟`, `接受吸烟`, `是否接受抽烟`, `是否接受吸烟` |
| `accept_drinking` | `接受喝酒`, `接受饮酒`, `是否接受喝酒`, `是否接受饮酒` |
| `accept_marital_status` | `接受婚况`, `可接受婚况`, `可接受婚姻状态` |
| `has_children` | `有无孩子`, `是否有孩子`, `是否已育` |
| `want_children` | `是否想要孩子`, `想要孩子`, `生育计划`, `孩子计划` |
| `accept_partner_children` | `接受对方孩子`, `是否接受对方有孩子`, `是否接受伴侣有孩子` |
| `marriage_timeline` | `结婚时间`, `结婚计划`, `结婚节奏` |
| `family_background` | `家庭情况`, `家庭背景` |
| `profile_status` | `资料状态`, `档案状态` |
| `last_active_at` | `最近活跃时间`, `最后活跃时间` |
| `verified_level` | `认证等级`, `认证级别` |
| `notes` | `备注`, `说明` |
