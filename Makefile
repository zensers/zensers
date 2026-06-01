# Zensers Makefile
# 常用命令速查

.PHONY: help install install-dev install-prod update-lock test test-cov test-e2e lint format clean docker-build docker-up docker-down docker-logs release

# 默认目标
help:
	@echo "Zensers 开发命令"
	@echo ""
	@echo "安装命令:"
	@echo "  make install      - 安装开发环境依赖"
	@echo "  make install-dev  - 安装开发工具"
	@echo "  make install-prod - 安装生产环境依赖(锁定版本)"
	@echo "  make update-lock  - 更新锁定版本文件"
	@echo ""
	@echo "测试命令:"
	@echo "  make test         - 运行单元测试"
	@echo "  make test-cov     - 运行测试并生成覆盖率报告"
	@echo "  make test-e2e     - 运行端到端测试"
	@echo "  make test-all     - 运行所有测试"
	@echo ""
	@echo "代码质量:"
	@echo "  make lint         - 运行代码检查"
	@echo "  make format       - 格式化代码"
	@echo "  make type-check   - 运行类型检查"
	@echo ""
	@echo "其他:"
	@echo "  make clean        - 清理缓存文件"
	@echo "  make dev          - 启动开发模式"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build - 构建Docker镜像"
	@echo "  make docker-up    - 启动Docker服务"
	@echo "  make docker-down  - 停止Docker服务"
	@echo "  make docker-logs  - 查看Docker日志"
	@echo ""
	@echo "发布:"
	@echo "  make release      - 创建版本标签并推送"

# ==================== 安装命令 ====================

install:
	pip install -r requirements.txt

install-dev: install
	pip install -r requirements-dev.txt

install-prod:
	pip install -r requirements-lock.txt

update-lock:
	@echo "更新锁定版本文件..."
	pip install pip-tools
	pip-compile requirements.txt -o requirements-lock.txt --generate-hashes
	@echo "完成! 请检查 requirements-lock.txt"

# ==================== 测试命令 ====================

test:
	pytest tests/unit -v

test-cov:
	pytest tests/unit -v --cov=src --cov-report=term-missing --cov-report=html

test-integration:
	pytest tests/integration -v

test-e2e:
	pytest tests/e2e -v --timeout=3600

test-all:
	pytest -v --cov=src --cov-report=term-missing

# ==================== 代码质量 ====================

lint:
	flake8 src tests
	pylint src
	bandit -r src

format:
	black src tests
	isort src tests

type-check:
	mypy src

# ==================== 其他命令 ====================

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage" -delete
	rm -rf htmlcov
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	@echo "清理完成!"

dev:
	@echo "启动开发模式..."
	@echo "请运行: python -m src.cli.main"

# ==================== 安全检查 ====================

security-check:
	safety check
	bandit -r src -f json -o bandit-report.json
	@echo "安全检查完成，报告: bandit-report.json"

# ==================== Docker 命令 ====================

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

# ==================== 发布命令 ====================

release:
	@echo "Creating release v$$(cat VERSION)..."
	git tag -a v$$(cat VERSION) -m "Release v$$(cat VERSION)"
	git push origin v$$(cat VERSION)
