import React, { useEffect, useState } from 'react';
import { FileUp, Send } from 'lucide-react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const API_BASE = import.meta.env.VITE_API_BASE || '/api';
window.__AI_EXTRACTOR_UI_VERSION__ = 'chat-ui-2026-06-24';

function hideStaticFallbackWhenChatIsVisible() {
  window.requestAnimationFrame(() => {
    const chatWindow = document.querySelector('.chat-window');
    const fallback = document.getElementById('static-fallback');
    const rect = chatWindow?.getBoundingClientRect();
    if (fallback && rect && rect.width > 100 && rect.height > 100) {
      fallback.setAttribute('hidden', 'true');
    }
  });
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
    hideStaticFallbackWhenChatIsVisible();
  }, []);
  const [text, setText] = useState('');
  const [files, setFiles] = useState([]);
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: '你好，我可以识别你上传的图片或文件，并把结构化结果保存到后台数据库。',
    },
  ]);
  const [loading, setLoading] = useState(false);

  function describeFiles(selectedFiles) {
    if (selectedFiles.length === 0) return '';
    return selectedFiles.map((file) => file.name).join('、');
  }

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
            : '识别完成。当前未配置数据库，因此结果没有持久化保存。',
        },
      ]);
      setText('');
      setFiles([]);
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

  return <main className="chat-shell">
    <section className="chat-window" aria-label="AI Extractor chat">
      <header className="chat-header">
        <div>
          <h1>AI Extractor</h1>
          <p>上传图片或文件，识别结果会保存到后台数据库。</p>
        </div>
      </header>

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
    </section>
  </main>;
}

createRoot(document.getElementById('root')).render(<ErrorBoundary><App /></ErrorBoundary>);
