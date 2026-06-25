import React, { useEffect, useRef, useState } from 'react';
import { Database, FileUp, MessageCircle, RefreshCw, Send } from 'lucide-react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const API_BASE = import.meta.env.VITE_API_BASE || '/api';
window.__AI_EXTRACTOR_UI_VERSION__ = 'chat-ui-2026-06-24-admin';

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



function getSavedFileName(filePath) {
  return String(filePath || '').split(/[\\/]/).pop() || '原文件';
}

function isImageFile(filePath) {
  return /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(getSavedFileName(filePath));
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function downloadExcel(record) {
  if (!record) return;
  const response = await fetch(`${API_BASE}/export/excel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ data: record.result_json || {} }),
  });
  if (!response.ok) throw new Error('Excel 导出失败');
  const blob = await response.blob();
  downloadBlob(blob, `${record.id || 'result'}.xlsx`);
}

function formatCellValue(value) {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function buildResultRows(result) {
  if (!result || typeof result !== 'object') return [];
  const rows = [];
  const sections = Array.isArray(result.sections) ? result.sections : [];

  sections.forEach((section) => {
    const fields = Array.isArray(section?.fields) ? section.fields : [];
    fields.forEach((field) => {
      rows.push({
        section: section?.section_name || '未分组',
        name: field?.field_name || '未命名字段',
        value: formatCellValue(field?.field_value),
        status: field?.status || '—',
        source: field?.source_hint || '—',
      });
    });
  });

  const fields = Array.isArray(result.fields) ? result.fields : [];
  fields.forEach((field) => {
    rows.push({
      section: '字段',
      name: field?.key || field?.field_name || '未命名字段',
      value: formatCellValue(field?.value ?? field?.field_value),
      status: field?.status || '—',
      source: field?.source_hint || '—',
    });
  });

  if (rows.length === 0 && result.summary) {
    rows.push({ section: '摘要', name: 'summary', value: formatCellValue(result.summary), status: '—', source: '—' });
  }

  return rows;
}

function ResultTable({ record, onEdit, onDelete }) {
  if (!record) return <div className="result-empty">选择一条记录后查看结构化结果。</div>;

  const result = record.result_json || {};
  const documentInfo = result.document_info || {};
  const rows = buildResultRows(result);
  const warnings = Array.isArray(result.warnings) ? result.warnings : [];
  const savedFiles = Array.isArray(record.saved_files) ? record.saved_files : [];

  return <div className="result-panel">
    <section className="result-summary">
      <h2>{documentInfo.title || record.input_text || '未命名记录'}</h2>
      <dl>
        <div><dt>记录 ID</dt><dd>{record.id}</dd></div>
        <div><dt>创建时间</dt><dd>{record.created_at || '—'}</dd></div>
        <div><dt>文档编号</dt><dd>{documentInfo.id || '—'}</dd></div>
        <div><dt>置信度</dt><dd>{documentInfo.confidence ?? '—'}</dd></div>
      </dl>
      <div className="result-actions">
        <button type="button" onClick={() => downloadExcel(record)}>导出 Excel</button>
        <button type="button" onClick={() => onEdit(record)}>编辑</button>
        <button type="button" className="danger" onClick={() => onDelete(record)}>删除</button>
      </div>
    </section>

    {savedFiles.length > 0 && <section className="source-files">
      <h3>原图片/文件</h3>
      <div className="source-file-grid">
        {savedFiles.map((filePath, index) => {
          const fileUrl = `${API_BASE}/admin/results/${record.id}/files/${index}`;
          const fileName = getSavedFileName(filePath);
          return <article className="source-file-card" key={`${fileName}-${index}`}>
            {isImageFile(filePath) && <img src={fileUrl} alt={fileName} loading="lazy" />}
            <span>{fileName}</span>
            <a href={fileUrl} download={fileName}>下载原图/文件</a>
          </article>;
        })}
      </div>
    </section>}

    <div className="result-table-wrap">
      <table className="result-table">
        <thead>
          <tr>
            <th>分组</th>
            <th>字段</th>
            <th>值</th>
            <th>状态</th>
            <th>来源</th>
          </tr>
        </thead>
        <tbody>
          {rows.length > 0 ? rows.map((row, index) => <tr key={`${row.section}-${row.name}-${index}`}>
            <td>{row.section}</td>
            <td>{row.name}</td>
            <td>{row.value}</td>
            <td><span className={`status-pill status-${row.status}`}>{row.status}</span></td>
            <td>{row.source}</td>
          </tr>) : <tr><td colSpan="5" className="table-empty">暂无可展示字段。</td></tr>}
        </tbody>
      </table>
    </div>

    {warnings.length > 0 && <section className="warnings-panel">
      <strong>警告</strong>
      <ul>{warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>
    </section>}
  </div>;
}

function App() {
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
  const [adminQuery, setAdminQuery] = useState('');
  const [editorMode, setEditorMode] = useState(null);
  const [editorRecordId, setEditorRecordId] = useState('');
  const [editorInputText, setEditorInputText] = useState('');
  const [editorResultJson, setEditorResultJson] = useState('');
  const [editorSavedFiles, setEditorSavedFiles] = useState('');
  const [editorError, setEditorError] = useState('');
  const submittingRef = useRef(false);

  function describeFiles(selectedFiles) {
    if (selectedFiles.length === 0) return '';
    return selectedFiles.map((file) => file.name).join('、');
  }

  async function loadAdminResults() {
    setAdminLoading(true);
    setAdminError('');
    try {
      const params = new URLSearchParams();
      if (adminQuery.trim()) params.set('query', adminQuery.trim());
      const response = await fetch(`${API_BASE}/admin/results${params.toString() ? `?${params}` : ''}`);
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



  function openEditEditor(record) {
    setEditorMode('edit');
    setEditorRecordId(record.id);
    setEditorInputText(record.input_text || '');
    setEditorResultJson(JSON.stringify(record.result_json || {}, null, 2));
    setEditorSavedFiles((record.saved_files || []).join('\n'));
    setEditorError('');
  }

  function closeEditor() {
    setEditorMode(null);
    setEditorError('');
  }

  async function saveEditor() {
    setEditorError('');
    let resultJson;
    try {
      resultJson = JSON.parse(editorResultJson || '{}');
    } catch (error) {
      setEditorError('结果 JSON 格式不正确，请检查后再保存。');
      return;
    }

    const payload = {
      input_text: editorInputText,
      result_json: resultJson,
      saved_files: editorSavedFiles.split('\n').map((item) => item.trim()).filter(Boolean),
    };
    const response = await fetch(`${API_BASE}/admin/results/${editorRecordId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const json = await response.json();
    if (!response.ok || json.code !== 0) {
      setEditorError(json.message || '保存失败。');
      return;
    }
    setSelectedRecord(json.data);
    closeEditor();
    loadAdminResults();
  }

  async function deleteRecord(record) {
    if (!record || !window.confirm(`确认删除记录 ${record.id}？`)) return;
    const response = await fetch(`${API_BASE}/admin/results/${record.id}`, { method: 'DELETE' });
    const json = await response.json();
    if (!response.ok || json.code !== 0) {
      setAdminError(json.message || '删除失败。');
      return;
    }
    setSelectedRecord(null);
    loadAdminResults();
  }

  useEffect(() => {
    if (view === 'admin') loadAdminResults();
  }, [view]);

  async function submit() {
    if (submittingRef.current || (!text.trim() && files.length === 0)) return;
    submittingRef.current = true;

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
      submittingRef.current = false;
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
          <div className="admin-toolbar-actions">
            <input className="admin-search" value={adminQuery} onChange={(event) => setAdminQuery(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') loadAdminResults(); }} placeholder="搜索字段/说明/文件" />
            <button onClick={loadAdminResults} disabled={adminLoading}><RefreshCw size={16} />{adminLoading ? '查询中' : '查询/刷新'}</button>
          </div>
        </div>
        {adminError && <p className="admin-error">{adminError}</p>}
        {editorMode && <section className="admin-editor">
          <div className="admin-editor-header">
            <strong>编辑记录</strong>
            <button type="button" onClick={closeEditor}>关闭</button>
          </div>
          <label>输入说明
            <input value={editorInputText} onChange={(event) => setEditorInputText(event.target.value)} placeholder="输入说明" />
          </label>
          <label>结果 JSON
            <textarea value={editorResultJson} onChange={(event) => setEditorResultJson(event.target.value)} rows={8} />
          </label>
          <label>原文件路径（每行一个，可选）
            <textarea value={editorSavedFiles} onChange={(event) => setEditorSavedFiles(event.target.value)} rows={3} />
          </label>
          {editorError && <p className="admin-error">{editorError}</p>}
          <button type="button" onClick={saveEditor}>保存</button>
        </section>}
        <div className="admin-content">
          <div className="record-list">
            {adminItems.length === 0 && <p className="empty-state">暂无保存记录。</p>}
            {adminItems.map((item) => <button className="record-card" key={item.id} onClick={() => setSelectedRecord(item)}>
              <strong>{item.result_json?.document_info?.title || item.input_text || '未命名记录'}</strong>
              <span>{item.created_at}</span>
              <small>{item.id}</small>
            </button>)}
          </div>
          <ResultTable record={activeRecord} onEdit={openEditEditor} onDelete={deleteRecord} />
        </div>
      </section>}
    </section>
  </main>;
}

createRoot(document.getElementById('root')).render(<ErrorBoundary><App /></ErrorBoundary>);
