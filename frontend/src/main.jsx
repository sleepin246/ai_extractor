import React, { useEffect, useState } from 'react';
import { Database, FileUp, MessageCircle, RefreshCw, Send } from 'lucide-react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const API_BASE = import.meta.env.VITE_API_BASE || '/api';
window.__AI_EXTRACTOR_UI_VERSION__ = 'chat-ui-2026-06-24-admin';

function hideStaticFallback() {
  document.getElementById('static-fallback')?.setAttribute('hidden', 'true');
}

function AppErrorFallback() {
  return <main className="chat-shell">
    <section className="chat-window error-window">
      <h1>AI Extractor</h1>
      <p>聊天界面加载失败，请刷新页面；也可以使用基础提交表单。</p>
      <form action="/api/parse" method="post" encType="multipart/form-data" className="fallback-form">
        <textarea name="text" placeholder="输入说明，或选择图片/文件后提交..." />
        <input name="files" type="file" multiple />
        <button type="submit">提交识别</button>
      </form>
    </section>
  </main>;
}

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error) {
    console.error('AI Extractor UI failed to render', error);
  }

  render() {
    if (this.state.hasError) return <AppErrorFallback />;
    return this.props.children;
  }
}

function App() {
  useEffect(() => {
    hideStaticFallback();
  }, []);

  const [view, setView] = useState('chat');
  const [text, setText] = useState('');
  const [files, setFiles] = useState([]);
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: '你好，我可以识别你上传的图片或文件，并把结构化结果保存到后台数据库。',
    },
  ]);
  const [loading, setLoading] = useState(false);
  const [adminItems, setAdminItems] = useState([]);
  const [adminLoading, setAdminLoading] = useState(false);
  const [databaseEnabled, setDatabaseEnabled] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [adminError, setAdminError] = useState('');

  function describeFiles(selectedFiles) {
    if (selectedFiles.length === 0) return '';
    return selectedFiles.map((file) => file.name).join('、');
  }

  async function loadAdminResults() {
    setAdminLoading(true);
    setAdminError('');
    try {
      const response = await fetch(`${API_BASE}/admin/results`);
      const json = await response.json();
      if (!response.ok || json.code !== 0) {
        throw new Error(json.message || '后台数据加载失败。');
      }
      setAdminItems(json.data.items || []);
      setDatabaseEnabled(Boolean(json.data.database_enabled));
    } catch (error) {
      setAdminError(error.message || '后台数据加载失败。');
    } finally {
      setAdminLoading(false);
    }
  }

  useEffect(() => {
    if (view === 'admin') loadAdminResults();
  }, [view]);

  async function submit() {
    if (!text.trim() && files.length === 0) return;

    const userMessage = text.trim() || `上传了 ${files.length} 个文件：${describeFiles(files)}`;
    setMessages((items) => [...items, { role: 'user', content: userMessage }]);
    setLoading(true);

    try {
      const form = new FormData();
      form.append('text', text);
      files.forEach((file) => form.append('files', file));

      const response = await fetch(`${API_BASE}/parse`, { method: 'POST', body: form });
      const json = await response.json();

      if (!response.ok || json.code !== 0) {
        throw new Error(json.message || '识别失败，请稍后再试。');
      }

      const recordId = json.data?.record_id;
      setMessages((items) => [
        ...items,
        {
          role: 'assistant',
          content: recordId
            ? `识别完成，结果已保存到后台数据库。记录 ID：${recordId}`
            : '识别完成，但后端没有返回数据库记录 ID。请确认 Render 已绑定 PostgreSQL 并设置 DATABASE_URL。',
        },
      ]);
      setText('');
      setFiles([]);
      if (recordId) loadAdminResults();
    } catch (error) {
      setMessages((items) => [
        ...items,
        { role: 'assistant', content: error.message || '识别请求失败，请检查服务配置。' },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  function openAdmin() {
    setView('admin');
  }

  function openChat() {
    setView('chat');
  }

  const activeRecord = selectedRecord || adminItems[0] || null;

  return <main className="chat-shell">
    <section className="chat-window" aria-label="AI Extractor">
      <header className="chat-header">
        <div>
          <h1>AI Extractor</h1>
          <p>{view === 'chat' ? '上传图片或文件，识别结果会保存到后台数据库。' : '查看 PostgreSQL 中保存的结构化识别结果。'}</p>
        </div>
        <nav className="view-tabs" aria-label="页面切换">
          <button className={view === 'chat' ? 'active' : ''} onClick={openChat}><MessageCircle size={18} />对话</button>
          <button className={view === 'admin' ? 'active' : ''} onClick={openAdmin}><Database size={18} />后台</button>
        </nav>
      </header>

      {view === 'chat' ? <>
        <div className="messages">
          {messages.map((message, index) => <div key={index} className={`message-row ${message.role}`}>
            <div className="bubble">{message.content}</div>
          </div>)}
          {loading && <div className="message-row assistant"><div className="bubble typing">正在识别并保存...</div></div>}
        </div>

        {files.length > 0 && <div className="file-preview">已选择：{describeFiles(files)}</div>}

        <div className="composer">
          <label className="upload" title="选择文件">
            <FileUp size={20} />
            <input multiple type="file" onChange={(event) => setFiles([...event.target.files])} />
          </label>
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入说明，或直接上传图片/文件后发送..."
            rows={1}
          />
          <button onClick={submit} disabled={loading || (!text.trim() && files.length === 0)} aria-label="发送">
            <Send size={20} />
          </button>
        </div>
      </> : <section className="admin-view">
        <div className="admin-toolbar">
          <div>
            <strong>{databaseEnabled ? '数据库已连接' : '数据库未连接'}</strong>
            <p>{databaseEnabled ? `共 ${adminItems.length} 条记录` : '请在 Render 为 Web Service 设置 DATABASE_URL。'}</p>
          </div>
          <button onClick={loadAdminResults} disabled={adminLoading}><RefreshCw size={16} />{adminLoading ? '加载中' : '刷新'}</button>
        </div>
        {adminError && <p className="admin-error">{adminError}</p>}
        <div className="admin-content">
          <div className="record-list">
            {adminItems.length === 0 && <p className="empty-state">暂无保存记录。</p>}
            {adminItems.map((item) => <button className="record-card" key={item.id} onClick={() => setSelectedRecord(item)}>
              <strong>{item.result_json?.document_info?.title || item.input_text || '未命名记录'}</strong>
              <span>{item.created_at}</span>
              <small>{item.id}</small>
            </button>)}
          </div>
          <pre className="record-json">{activeRecord ? JSON.stringify(activeRecord.result_json, null, 2) : '选择一条记录后查看结构化 JSON。'}</pre>
        </div>
      </section>}
    </section>
  </main>;
}

createRoot(document.getElementById('root')).render(<ErrorBoundary><App /></ErrorBoundary>);
