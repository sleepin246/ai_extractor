import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Download, FileUp, Send } from 'lucide-react';
import './styles.css';

const API_BASE = import.meta.env.VITE_API_BASE || '/api';

function App() {
  const [text, setText] = useState('');
  const [files, setFiles] = useState([]);
  const [messages, setMessages] = useState([
    { role: 'assistant', content: '上传文字、图片、语音或文件，我会解析为可编辑 JSON。' },
  ]);
  const [result, setResult] = useState(null);
  const [jsonText, setJsonText] = useState('{}');
  const [jsonError, setJsonError] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit() {
    if (!text && files.length === 0) return;
    setLoading(true);
    setMessages((items) => [...items, { role: 'user', content: text || `上传了 ${files.length} 个文件` }]);
    const form = new FormData();
    form.append('text', text);
    files.forEach((file) => form.append('files', file));
    const response = await fetch(`${API_BASE}/parse`, { method: 'POST', body: form });
    const json = await response.json();
    setResult(json.data.result);
    setJsonText(JSON.stringify(json.data.result, null, 2));
    setJsonError('');
    setMessages((items) => [...items, { role: 'assistant', content: '已完成解析，可在右侧/下方编辑 JSON 并导出。' }]);
    setText('');
    setFiles([]);
    setLoading(false);
  }

  async function download(format) {
    const response = await fetch(`${API_BASE}/export/${format}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data: result }),
    });
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `ai-extractor-result.${format === 'excel' ? 'xlsx' : format === 'markdown' ? 'md' : format}`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return <main className="app-shell">
    <section className="chat-panel">
      <header><h1>AI Extractor</h1><p>文字 / 图片 / 语音 / 文件 → 结构化 JSON</p></header>
      <div className="messages">{messages.map((message, index) => <div key={index} className={`bubble ${message.role}`}>{message.content}</div>)}</div>
      <div className="composer">
        <textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="输入需要解析的文本，也可以上传文件..." />
        <label className="upload"><FileUp size={18} />选择文件<input multiple type="file" onChange={(event) => setFiles([...event.target.files])} /></label>
        <button onClick={submit} disabled={loading}><Send size={18} />{loading ? '解析中' : '发送'}</button>
      </div>
      {files.length > 0 && <p className="hint">已选择 {files.length} 个文件</p>}
    </section>
    <section className="result-panel">
      <h2>结构化结果</h2>
      <textarea className="json-editor" value={jsonText} onChange={(event) => {
        const value = event.target.value;
        setJsonText(value);
        try {
          const parsed = JSON.parse(value || '{}');
          setResult(parsed);
          setJsonError('');
        } catch {
          setJsonError('JSON 格式暂不合法，修正后即可导出。');
        }
      }} />
      {jsonError && <p className="error">{jsonError}</p>}
      <div className="exports">{['json', 'excel', 'markdown', 'zip'].map((format) => <button key={format} disabled={!result} onClick={() => download(format)}><Download size={16} />{format.toUpperCase()}</button>)}</div>
    </section>
  </main>;
}

createRoot(document.getElementById('root')).render(<App />);
