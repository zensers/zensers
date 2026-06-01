# Contributing to Zensers / 贡献指南

## Welcome / 欢迎

Thank you for your interest in contributing to Zensers! We welcome contributions from the community.

感谢您有兴趣为 Zensers 做出贡献！我们欢迎来自社区的贡献。

---

## How to Contribute / 如何贡献

### Report Bugs / 报告Bug

1. Check existing issues to avoid duplicates
2. Use the bug report template
3. Include: OS, Python version, steps to reproduce, expected vs actual behavior

### Suggest Features / 建议功能

1. Check existing issues and roadmap
2. Use the feature request template
3. Describe the use case and expected behavior

### Submit Pull Requests / 提交PR

See PR process below.

---

## Development Setup / 开发环境设置

### Prerequisites / 前置条件

- Python 3.10+
- Git
- (Optional) Node.js 18+ for web components

### Setup Steps / 设置步骤

```bash
# Clone the repository
git clone https://github.com/sunchaokun/zensers.git
cd zensers

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys

# Run tests
pytest

# Run the application
python desktop_app.py
```

---

## Code Style / 代码风格

### Python

- Follow **PEP 8** conventions
- Use **type hints** for all function signatures
- Use **docstrings** for public functions and classes
- Max line length: 100 characters
- Use `pyright` for type checking

Example:
```python
def process_research(topic: str, requirements: list[str]) -> ResearchResult:
    """Process a research task and return results.
    
    Args:
        topic: The research topic.
        requirements: List of research requirements.
    
    Returns:
        ResearchResult object containing the report.
    """
    ...
```

### TypeScript (Web Components)

- Follow ESLint configuration in `web/`
- Use strict mode
- Prefer functional components

---

## Commit Convention / 提交规范

We follow **Conventional Commits**:

| Type | Description |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Formatting, no code change |
| `refactor` | Code refactoring |
| `test` | Adding or updating tests |
| `chore` | Maintenance tasks |

Format:
```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

Examples:
```
feat(agents): add market analysis agent
fix(skills): resolve web scraper timeout issue
docs(readme): update installation instructions
test(core): add orchestrator unit tests
```

---

## Pull Request Process / PR流程

### Step 1: Fork and Branch / Fork并创建分支

```bash
# Fork the repo on GitHub, then:
git clone https://github.com/YOUR_USERNAME/zensers.git
cd zensers
git checkout -b feat/your-feature-name
```

### Step 2: Make Changes / 进行修改

- Write clean, documented code
- Add tests for new functionality
- Ensure all tests pass: `pytest`
- Run type check: `pyright`

### Step 3: Commit and Push / 提交并推送

```bash
git add .
git commit -m "feat(scope): your changes"
git push origin feat/your-feature-name
```

### Step 4: Create Pull Request / 创建PR

1. Go to GitHub and create a PR
2. Fill in the PR template
3. Link related issues
4. Request review from maintainers

### PR Requirements / PR要求

- [ ] All tests pass
- [ ] Code follows style guidelines
- [ ] Documentation updated (if needed)
- [ ] Commit messages follow convention
- [ ] No merge conflicts

---

## Issue Templates / Issue模板

### Bug Report

```markdown
**Description**
A clear description of the bug.

**To Reproduce**
Steps to reproduce:
1. Run `...`
2. Click `...`
3. See error

**Expected Behavior**
What should happen.

**Environment**
- OS: [e.g., Windows 11]
- Python: [e.g., 3.11.0]
- Zensers version: [e.g., 1.0.0]

**Logs**
```
Paste relevant logs here
```
```

### Feature Request

```markdown
**Problem**
What problem does this feature solve?

**Solution**
Describe the proposed solution.

**Alternatives**
Any alternative solutions considered?

**Additional Context**
Any other relevant information.
```

---

## Questions? / 有问题？

- Open a [GitHub Issue](https://github.com/sunchaokun/zensers/issues)
- Check [Documentation](docs/)

Thank you for contributing! / 感谢您的贡献！
