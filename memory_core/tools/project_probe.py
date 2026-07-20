"""ProjectProbe — 只读探测项目元信息。

探测语言/框架/工具链/git/数据库/项目类型/项目概述。
所有探测方法只读不写，失败返回默认值（不抛异常）。
"""
from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# 需要跳过的目录
_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".eggs", "*.egg-info",
}

# 语言检测的文件 -> 语言映射
_LANG_CONFIG_FILES: dict[str, str] = [
    # (文件名, 语言, 置信度标记)
    ("pyproject.toml", "Python"),
    ("requirements.txt", "Python"),
    ("setup.py", "Python"),
    ("setup.cfg", "Python"),
    ("Pipfile", "Python"),
    ("poetry.lock", "Python"),
    ("package.json", "JavaScript/TypeScript"),
    ("go.mod", "Go"),
    ("Cargo.toml", "Rust"),
    ("pom.xml", "Java"),
    ("build.gradle", "Java"),
    ("build.gradle.kts", "Java/Kotlin"),
    ("Gemfile", "Ruby"),
    ("composer.json", "PHP"),
    ("package-lock.json", "JavaScript/TypeScript"),
    ("yarn.lock", "JavaScript/TypeScript"),
    ("CMakeLists.txt", "C/C++"),
    ("Makefile", "C/C++"),
    ("go.sum", "Go"),
    ("*.csproj", "C#"),
    ("*.sln", "C#"),
    ("project.clj", "Clojure"),
    ("mix.exs", "Elixir"),
    ("rebar.config", "Erlang"),
    ("*.hs", "Haskell"),
    ("*.exs", "Elixir"),
    ("*.erl", "Erlang"),
    ("*.scala", "Scala"),
    ("*.kt", "Kotlin"),
    ("*.swift", "Swift"),
]

# 语言文件计数映射（扩展名 -> 语言）
_LANG_EXT_MAP: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".jsx": "JavaScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".scala": "Scala",
    ".cpp": "C++",
    ".c": "C",
    ".h": "C/C++",
    ".hpp": "C++",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".erl": "Erlang",
    ".hs": "Haskell",
    ".clj": "Clojure",
    ".lua": "Lua",
    ".r": "R",
    ".R": "R",
    ".sh": "Shell",
    ".bash": "Shell",
}

# 框架关键词映射
_FRAMEWORK_KEYWORDS: dict[str, str] = {
    "django": "Django",
    "flask": "Flask",
    "fastapi": "FastAPI",
    "celery": "Celery",
    "pytest": "pytest",
    "numpy": "NumPy",
    "pandas": "pandas",
    "scikit-learn": "scikit-learn",
    "torch": "PyTorch",
    "tensorflow": "TensorFlow",
    "express": "Express.js",
    "next": "Next.js",
    "nuxt": "Nuxt.js",
    "react": "React",
    "vue": "Vue.js",
    "angular": "Angular",
    "svelte": "Svelte",
    "nestjs": "NestJS",
    "rails": "Ruby on Rails",
    "sinatra": "Sinatra",
    "laravel": "Laravel",
    "symfony": "Symfony",
    "spring": "Spring",
    "gin": "Gin",
    "fiber": "Fiber",
    "actix": "Actix",
    "rocket": "Rocket",
    "axum": "Axum",
    "aspnet": "ASP.NET",
    "dotnet": ".NET",
}

# 数据库关键词
_DB_KEYWORDS = [
    "postgres", "postgresql", "mysql", "sqlite", "mongo", "mongodb",
    "redis", "cassandra", "dynamodb", "mariadb", "oracle", "mssql",
    "sqlserver", "neo4j", "elasticsearch", "couchdb", "influxdb",
    "prisma", "typeorm", "sequelize", "sqlalchemy",
]


@dataclass
class ProjectInfo:
    """探测到的项目元信息。"""
    primary_language: str = ""
    framework: str = ""
    project_type: str = ""
    databases: list[str] = field(default_factory=list)
    toolchain: list[dict[str, str]] = field(default_factory=list)
    git_remote_url: str = ""
    git_branch: str = ""
    project_overview: str = ""


class ProjectProbe:
    """只读探测项目元信息。

    所有探测方法都是 try/except 包裹，失败返回默认值。
    不扫描 .git/, node_modules/, __pycache__/ 等大目录。
    """

    def __init__(self, target: Path) -> None:
        self.target = target.resolve()
        self._file_cache: dict[str, list[Path]] = {}

    def probe(self) -> ProjectInfo:
        """执行完整探测，返回 ProjectInfo。"""
        info = ProjectInfo()

        try:
            info.primary_language = self._detect_language()
        except Exception as exc:
            logger.debug("Language detection failed: %s", exc)

        try:
            info.framework = self._detect_framework()
        except Exception as exc:
            logger.debug("Framework detection failed: %s", exc)

        try:
            info.project_type = self._detect_project_type()
        except Exception as exc:
            logger.debug("Project type detection failed: %s", exc)

        try:
            info.databases = self._detect_databases()
        except Exception as exc:
            logger.debug("Database detection failed: %s", exc)

        try:
            info.toolchain = self._detect_toolchain()
        except Exception as exc:
            logger.debug("Toolchain detection failed: %s", exc)

        try:
            info.git_remote_url, info.git_branch = self._detect_git_info()
        except Exception as exc:
            logger.debug("Git info detection failed: %s", exc)

        try:
            info.project_overview = self._extract_readme_summary()
        except Exception as exc:
            logger.debug("README summary extraction failed: %s", exc)

        return info

    def _should_skip_dir(self, name: str) -> bool:
        """判断是否应跳过该目录。"""
        if name in _SKIP_DIRS:
            return True
        # Skip hidden directories except .github (for CI detection)
        if name.startswith(".") and name != ".github":
            return True
        return False

    def _find_files(self, pattern: str) -> list[Path]:
        """在目标目录中查找匹配模式的文件（跳过忽略目录）。"""
        if pattern in self._file_cache:
            return self._file_cache[pattern]

        results: list[Path] = []
        pattern_lower = pattern.lower()

        for root, dirs, files in os.walk(self.target):
            # 跳过忽略的目录
            dirs[:] = [d for d in dirs if not self._should_skip_dir(d)]

            for fname in files:
                if fname.lower() == pattern_lower:
                    results.append(Path(root) / fname)
                elif pattern.startswith("*") and pattern.endswith("*"):
                    # 通配符匹配，如 *.csproj
                    inner = pattern[1:-1]
                    if fname.endswith(inner):
                        results.append(Path(root) / fname)

        self._file_cache[pattern] = results
        return results

    def _detect_language(self) -> str:
        """通过配置文件检测主语言。"""
        # 策略 1: 通过配置文件检测
        lang_counts: dict[str, int] = {}

        for fname, language in _LANG_CONFIG_FILES:
            if "*" in fname:
                # 通配符匹配
                matched = self._find_files(fname)
                if matched:
                    lang_counts[language] = lang_counts.get(language, 0) + len(matched)
            else:
                matched = self._find_files(fname)
                if matched:
                    lang_counts[language] = lang_counts.get(language, 0) + 1

        if lang_counts:
            # 返回计数最高的语言
            return max(lang_counts, key=lang_counts.get)

        # 策略 2: 通过文件扩展名统计
        ext_counts: dict[str, int] = {}
        for root, dirs, files in os.walk(self.target):
            dirs[:] = [d for d in dirs if not self._should_skip_dir(d)]
            for fname in files:
                ext = Path(fname).suffix.lower()
                if ext in _LANG_EXT_MAP:
                    lang = _LANG_EXT_MAP[ext]
                    ext_counts[lang] = ext_counts.get(lang, 0) + 1

        if ext_counts:
            return max(ext_counts, key=ext_counts.get)

        return ""

    def _detect_framework(self) -> str:
        """通过依赖文件中的关键词检测框架。"""
        frameworks_found: list[str] = []

        # 搜索配置文件
        config_files = [
            "pyproject.toml", "requirements.txt", "package.json",
            "Cargo.toml", "Gemfile", "composer.json", "pom.xml",
            "build.gradle", "build.gradle.kts", "go.mod",
        ]

        for cf in config_files:
            matched = self._find_files(cf)
            for fpath in matched:
                try:
                    content = fpath.read_text(encoding="utf-8")
                    content_lower = content.lower()
                    for keyword, framework in _FRAMEWORK_KEYWORDS.items():
                        if keyword in content_lower:
                            frameworks_found.append(framework)
                except (OSError, UnicodeDecodeError):
                    continue

        # 去重并返回主要框架
        if frameworks_found:
            # 返回出现次数最多的框架
            from collections import Counter
            counter = Counter(frameworks_found)
            return counter.most_common(1)[0][0]

        return ""

    def _detect_web_api_markers(self) -> int:
        """检测 Web/API 项目标记数量。"""
        count = 0
        for pattern in ["app.py", "main.py", "index.js", "server.js",
                        "app.js", "index.ts", "server.ts"]:
            if self._find_files(pattern):
                count += 1
        return count

    def _detect_cli_markers(self) -> int:
        """检测 CLI 工具标记数量。"""
        if self._find_files("cli.py") or self._find_files("cli.js"):
            return 1
        return 0

    def _detect_library_markers(self) -> int:
        """检测库/包项目标记数量。"""
        if self._find_files("setup.py") or self._find_files("pyproject.toml"):
            if self._find_files("src") and any(
                d.is_dir() for d in (self.target / "src").iterdir()
                if (self.target / "src").exists()
            ):
                return 1
        return 0

    def _detect_frontend_markers(self) -> int:
        """检测前端项目标记数量。"""
        if not self._find_files("package.json"):
            return 0
        count = 0
        for pattern in ["src/components", "src/pages", "public/index.html",
                        "vite.config.js", "vite.config.ts",
                        "webpack.config.js", "next.config.js"]:
            if self._find_files(pattern.split("/")[-1]):
                count += 1
        return count

    def _detect_mobile_markers(self) -> int:
        """检测移动端项目标记数量。"""
        count = 0
        for pattern in ["ios/", "android/", "Info.plist", "AndroidManifest.xml"]:
            if pattern.endswith("/"):
                if (self.target / pattern).is_dir():
                    count += 1
            elif self._find_files(pattern):
                count += 1
        return count

    def _detect_documentation_markers(self) -> int:
        """检测文档/笔记项目标记数量。"""
        if self._find_files("docs") and (self.target / "docs").is_dir():
            return 1
        return 0

    def _detect_microservices_markers(self) -> int:
        """检测微服务项目标记数量。"""
        if self._find_files("docker-compose.yml") or self._find_files("docker-compose.yaml"):
            return 1
        return 0

    def _detect_project_type(self) -> str:
        """通过目录结构和入口文件推断项目类型。"""
        markers: dict[str, int] = {}

        # Web/API 项目
        count = self._detect_web_api_markers()
        if count > 0:
            markers["web/api"] = count

        # CLI 工具
        count = self._detect_cli_markers()
        if count > 0:
            markers["cli-tool"] = count

        # 库/包
        count = self._detect_library_markers()
        if count > 0:
            markers["library"] = count

        # 前端项目
        count = self._detect_frontend_markers()
        if count > 0:
            markers["frontend"] = count

        # 移动端
        count = self._detect_mobile_markers()
        if count > 0:
            markers["mobile"] = count

        # 文档/笔记
        count = self._detect_documentation_markers()
        if count > 0 and not markers:
            markers["documentation"] = 1

        # 微服务
        count = self._detect_microservices_markers()
        if count > 0:
            markers["microservices"] = count

        if markers:
            return max(markers, key=markers.get)

        return ""

    def _detect_databases(self) -> list[str]:
        """通过配置文件和环境文件检测数据库。"""
        databases: set[str] = set()

        # 搜索的文件
        search_files = [
            "docker-compose.yml", "docker-compose.yaml",
            ".env", ".env.example", ".env.local",
            "pyproject.toml", "package.json",
            "config.yml", "config.yaml", "config.json",
            "settings.py", "database.yml",
            "appsettings.json", "application.yml",
        ]

        for sf in search_files:
            matched = self._find_files(sf)
            for fpath in matched:
                try:
                    content = fpath.read_text(encoding="utf-8")
                    content_lower = content.lower()
                    for db_keyword in _DB_KEYWORDS:
                        if db_keyword in content_lower:
                            # 标准化数据库名称
                            normalized = self._normalize_db_name(db_keyword)
                            databases.add(normalized)
                except (OSError, UnicodeDecodeError):
                    continue

        return sorted(databases)

    def _normalize_db_name(self, keyword: str) -> str:
        """标准化数据库关键词为可读名称。"""
        mapping = {
            "postgres": "PostgreSQL",
            "postgresql": "PostgreSQL",
            "mysql": "MySQL",
            "sqlite": "SQLite",
            "mongo": "MongoDB",
            "mongodb": "MongoDB",
            "redis": "Redis",
            "cassandra": "Cassandra",
            "dynamodb": "DynamoDB",
            "mariadb": "MariaDB",
            "oracle": "Oracle",
            "mssql": "SQL Server",
            "sqlserver": "SQL Server",
            "neo4j": "Neo4j",
            "elasticsearch": "Elasticsearch",
            "couchdb": "CouchDB",
            "influxdb": "InfluxDB",
            "prisma": "Prisma (ORM)",
            "typeorm": "TypeORM",
            "sequelize": "Sequelize",
            "sqlalchemy": "SQLAlchemy (ORM)",
        }
        return mapping.get(keyword, keyword.capitalize())

    def _detect_toolchain(self) -> list[dict[str, str]]:
        """检测项目使用的工具链（CI、linter、formatter 等）。"""
        tools: list[dict[str, str]] = []
        seen_names: set[str] = set()

        def _add_tool(name: str, config_file: str, category: str = "tool") -> None:
            if name not in seen_names:
                matched = self._find_files(config_file)
                if matched:
                    seen_names.add(name)
                    tools.append({
                        "name": name,
                        "config": config_file,
                        "category": category,
                    })

        # CI 工具
        _add_tool("GitHub Actions", "ci.yml", "ci")
        _add_tool("GitHub Actions", "ci.yaml", "ci")
        _add_tool("GitHub Actions", "main.yml", "ci")
        _add_tool("GitHub Actions", "main.yaml", "ci")
        _add_tool("GitHub Actions", "test.yml", "ci")
        _add_tool("GitLab CI", ".gitlab-ci.yml", "ci")
        _add_tool("Jenkins", "Jenkinsfile", "ci")
        _add_tool("CircleCI", "config.yml", "ci")
        _add_tool("Travis CI", ".travis.yml", "ci")
        _add_tool("Make", "Makefile", "build")

        # Linter
        _add_tool("Ruff", "ruff.toml", "linter")
        _add_tool("Flake8", ".flake8", "linter")
        _add_tool("Pylint", ".pylintrc", "linter")
        _add_tool("ESLint", ".eslintrc", "linter")
        _add_tool("ESLint", ".eslintrc.js", "linter")
        _add_tool("ESLint", ".eslintrc.json", "linter")
        _add_tool("ESLint", "eslint.config.js", "linter")
        _add_tool("Clippy", "Cargo.toml", "linter")  # Rust

        # Formatter
        _add_tool("Black", "pyproject.toml", "formatter")
        _add_tool("isort", "pyproject.toml", "formatter")
        _add_tool("Prettier", ".prettierrc", "formatter")
        _add_tool("Prettier", ".prettierrc.json", "formatter")
        _add_tool("Prettier", "prettier.config.js", "formatter")

        # 测试框架
        _add_tool("pytest", "pytest.ini", "test")
        _add_tool("pytest", "pyproject.toml", "test")
        _add_tool("Jest", "jest.config.js", "test")
        _add_tool("Jest", "jest.config.ts", "test")
        _add_tool("Mocha", ".mocharc.yml", "test")

        # 包管理
        _add_tool("pip", "requirements.txt", "package-manager")
        _add_tool("Poetry", "poetry.lock", "package-manager")
        _add_tool("npm", "package-lock.json", "package-manager")
        _add_tool("yarn", "yarn.lock", "package-manager")
        _add_tool("pnpm", "pnpm-lock.yaml", "package-manager")

        return tools

    def _detect_git_info(self) -> tuple[str, str]:
        """检测 git remote URL 和当前分支。"""
        remote_url = ""
        branch = ""

        try:
            result = subprocess.run(
                ["git", "-C", str(self.target), "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                remote_url = result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

        try:
            result = subprocess.run(
                ["git", "-C", str(self.target), "branch", "--show-current"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                branch = result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

        return remote_url, branch

    def _extract_readme_summary(self) -> str:
        """从 README.md 提取第一段非标题文本作为项目概述。"""
        readme_paths = (
            self._find_files("README.md")
            or self._find_files("readme.md")
            or self._find_files("README")
        )

        if not readme_paths:
            return ""

        readme = readme_paths[0]
        try:
            content = readme.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""

        lines = content.split("\n")
        summary_lines: list[str] = []
        in_title = True

        for line in lines:
            stripped = line.strip()
            # 跳过空行
            if not stripped:
                if in_title:
                    continue
                else:
                    break

            # 跳过标题
            if stripped.startswith("#"):
                continue

            # 跳过 badges/images
            if stripped.startswith("[!") or stripped.startswith("!["):
                continue

            # 找到第一段非标题文本
            if in_title:
                in_title = False

            summary_lines.append(stripped)
            if len(summary_lines) >= 3:
                break

        return " ".join(summary_lines).strip()
