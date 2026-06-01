# Zensers Web UI Development Plan

## 1. Requirements Analysis

### Core User Needs

1. **Chat Interaction** - Submit research tasks via natural language, system asks clarifying questions
2. **Progress Monitoring** - Real-time display of research progress, Agent execution status
3. **Report Preview** - Online preview of generated Word/PPT reports
4. **Version Management** - View, compare, rollback report versions

### Feature Modules

| Module | Function | Priority |
|------|------|--------|
| **Chat Interface** | Natural language input, multi-turn dialogue, clarification Q&A | 🔴 High |
| **Progress Panel** | Task status, Agent execution, timeline | 🔴 High |
| **Report Preview** | Word/PPT online preview, page turning, zoom | 🔴 High |
| **Task Management** | History tasks, task list, status filtering | 🟡 Medium |
| **Version Management** | Version comparison, rollback, diff highlighting | 🟡 Medium |
| **User Settings** | API configuration, preferences | 🟢 Low |

---

## 2. Technical Solution

### Backend (Existing Foundation)

| Component | Status | Description |
|------|------|------|
| `ResearchAPI` | ✅ Implemented | Research task interaction API |
| `DocumentAPI` | ✅ Implemented | Document generation/preview/version API |
| `PreviewGenerator` | ⚠️ Basic | Needs real preview improvements |
| FastAPI Support | ✅ Optional Dependency | Needs fastapi installed |

### Frontend Solution Options

| Solution | Pros | Cons | Recommendation |
|------|------|------|--------|
| **Streamlit** | Python native, fast development, suitable for data apps | Low customizability | ⭐⭐⭐⭐⭐ |
| **Gradio** | AI app dedicated, chat-friendly | Relatively simple features | ⭐⭐⭐⭐ |
| **React SPA** | Highly customizable, professional UI | Needs frontend development, complex deployment | ⭐⭐⭐ |
| **Vue + Vite** | Lightweight, progressive | Needs frontend development | ⭐⭐⭐ |

### Recommended: Streamlit

Rationale:
- Python native, no need to learn frontend framework
- Rapid prototype development
- Supports file preview, progress bar, chat interface
- Simple deployment (`streamlit run app.py`)

---

## 3. Streamlit UI Design

### Page Layout

```
┌─────────────────────────────────────────────────────────────┐
│  Zensers - Intelligent Market Research Platform  [Settings]  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────┐  ┌─────────────────────────────┐  │
│  │                     │  │                             │  │
│  │   Chat Interface     │  │   Report Preview            │  │
│  │                     │  │                             │  │
│  │   [Enter research...]│  │   ┌─────────────────────┐  │  │
│  │                     │  │   │                     │  │  │
│  │   System Reply:     │  │   │  Word Document      │  │  │
│  │   "Please confirm.."│  │   │                     │  │  │
│  │                     │  │   │  [Page 1/10]        │  │  │
│  │                     │  │   │                     │  │  │
│  └─────────────────────┘  │   └─────────────────────┘  │  │
│                            │                             │  │
│  ┌─────────────────────┐  └─────────────────────────────┘  │
│  │   Progress Panel    │                                    │
│  │                     │  ┌─────────────────────────────┐  │
│  │   ████████░░ 80%    │  │   Version History           │  │
│  │                     │  │                             │  │
│  │   ✓ Requirements    │  │   v3 (current) - 10:30     │  │
│  │   ✓ Data Collection │  │   v2 - 09:45               │  │
│  │   ⏳ Report Gen.    │  │   v1 - 09:00               │  │
│  │   ○ Quality Check   │  │                             │  │
│  │                     │  │   [Compare] [Rollback]      │  │
│  └─────────────────────┘  └─────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Core Feature Implementation

#### 1. Chat Interface
```python
import streamlit as st

# Chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# User input
if prompt := st.chat_input("Enter research topic or question..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    # Call API to process...
```

#### 2. Progress Panel
```python
import streamlit as st

# Progress bar
progress = st.progress(0.8)

# Status list
st.markdown("✅ Requirements Analysis")
st.markdown("✅ Data Collection")
st.markdown("⏳ Report Generation")
st.markdown("○ Quality Check")
```

#### 3. Report Preview
```python
import streamlit as st

# File path
doc_path = "output/report.docx"

# Option 1: Use docx preview (basic)
from docx import Document
doc = Document(doc_path)
for para in doc.paragraphs:
    st.write(para.text)

# Option 2: Convert to HTML for preview
st.markdown(html_content, unsafe_allow_html=True)

# Option 3: Provide download button
with open(doc_path, "rb") as f:
    st.download_button("Download Report", f, file_name="report.docx")
```

---

## 4. Development Plan

### Phase 1: MVP (1 Week)

| Task | Deliverable |
|------|--------|
| Streamlit project setup | `ui/app.py` |
| Chat interface | Research/clarification dialogue |
| Task initiation | API integration |
| Basic progress display | Progress bar, status list |
| File download | Download button |

### Phase 2: Feature Enhancement (1 Week)

| Task | Deliverable |
|------|--------|
| Online report preview | Word content display |
| Task history list | History task page |
| Agent execution details | Expandable Agent output |
| Error handling | User-friendly prompts |

### Phase 3: Advanced Features (1 Week)

| Task | Deliverable |
|------|--------|
| Version comparison | Diff highlighting |
| Research parameter configuration | Advanced settings panel |
| Multi-format export | PDF/HTML export |
| Deployment script | Dockerfile |

---

## 5. File Structure

```
ui/
├── app.py                 # Main application
├── pages/
│   ├── 1_TaskManagement.py    # Task list page
│   ├── 2_ReportPreview.py     # Report preview page
│   └── 3_Settings.py          # Settings page
├── components/
│   ├── chat.py            # Chat component
│   ├── progress.py        # Progress component
│   └── preview.py         # Preview component
├── api/
│   └── client.py          # API client
├── static/
│   └── style.css          # Custom styles
└── requirements.txt       # UI dependencies
```

---

## 6. Dependencies

```
streamlit>=1.28.0
streamlit-chat>=0.1.1
python-docx>=1.0.0
Pillow>=10.0.0
httpx>=0.25.0
```

---

## 7. Startup Commands

```bash
# Install dependencies
pip install streamlit streamlit-chat

# Start UI
streamlit run ui/app.py

# Or specify port
streamlit run ui/app.py --server.port 8501
```

---

## 8. Ready to Start Development?

Please confirm:
1. Whether to adopt the **Streamlit** solution?
2. Whether to develop MVP first (chat + progress + download)?
3. Whether report preview should start with basic version (text display), then be enhanced later?
