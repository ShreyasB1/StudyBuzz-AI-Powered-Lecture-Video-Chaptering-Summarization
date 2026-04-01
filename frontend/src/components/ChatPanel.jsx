import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { createChatStream } from '../services/api';

const markdownComponents = {
  p({ children }) {
    return <p className="markdown-paragraph">{children}</p>;
  },
  strong({ children }) {
    return <strong className="markdown-strong">{children}</strong>;
  },
  em({ children }) {
    return <em className="markdown-emphasis">{children}</em>;
  },
  blockquote({ children }) {
    return <blockquote className="markdown-blockquote">{children}</blockquote>;
  },
  ul({ children }) {
    return <ul className="markdown-list markdown-list-unordered">{children}</ul>;
  },
  ol({ children }) {
    return <ol className="markdown-list markdown-list-ordered">{children}</ol>;
  },
  li({ children }) {
    return <li className="markdown-list-item">{children}</li>;
  },
  a({ href, children }) {
    return (
      <a className="markdown-link" href={href} target="_blank" rel="noreferrer noopener">
        {children}
      </a>
    );
  },
  code({ inline, className, children, ...props }) {
    if (inline) {
      return (
        <code className="markdown-inline-code" {...props}>
          {children}
        </code>
      );
    }

    return (
      <code className={className ? `markdown-code ${className}` : 'markdown-code'} {...props}>
        {children}
      </code>
    );
  },
  pre({ children }) {
    return <pre className="markdown-pre">{children}</pre>;
  },
  h1({ children }) {
    return <h1 className="markdown-heading markdown-heading-1">{children}</h1>;
  },
  h2({ children }) {
    return <h2 className="markdown-heading markdown-heading-2">{children}</h2>;
  },
  h3({ children }) {
    return <h3 className="markdown-heading markdown-heading-3">{children}</h3>;
  },
  hr() {
    return <hr className="markdown-divider" />;
  },
};

export default function ChatPanel() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [useRag, setUseRag] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  async function handleSend(e) {
    if (e) e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMsg = input.trim();
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setInput('');
    setIsLoading(true);

    // Placeholder for the incoming assistant message
    const asstMsgId = Date.now();
    setMessages(prev => [
      ...prev,
      {
        id: asstMsgId,
        role: 'assistant',
        content: '',
        status: useRag ? 'Initializing...' : '',
        sources: [],
        extractions: {}, // maps id to extraction text
      }
    ]);

    try {
      const response = await createChatStream(userMsg, useRag);
      if (!response.ok) {
        throw new Error(`HTTP error ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let done = false;
      let buffer = '';

      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        if (value) {
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split('\n\n');
          buffer = parts.pop(); // keep remainder

          for (const part of parts) {
            const trimmed = part.trim();
            if (trimmed.startsWith('data: ')) {
              const jsonStr = trimmed.slice(6);
              try {
                const data = JSON.parse(jsonStr);
                
                setMessages(prev => prev.map(m => {
                  if (m.id !== asstMsgId) return m;

                  const nextMessage = { ...m };

                  if (data.type === 'status') {
                    nextMessage.status = data.message;
                  } else if (data.type === 'sources') {
                    nextMessage.sources = data.data; // [{id, video, chapter}]
                  } else if (data.type === 'extraction') {
                    nextMessage.extractions = { ...nextMessage.extractions, [data.id]: data.content };
                  } else if (data.type === 'chunk') {
                    nextMessage.content += data.text;
                  } else if (data.type === 'final_answer') {
                    nextMessage.status = ''; // clear status
                    if (data.data) {
                      // for normal text we might not need data.data if chunked, 
                      // but for rag, final_answer brings the whole text at once
                      nextMessage.content = data.data; 
                    }
                  } else if (data.type === 'error') {
                    nextMessage.content = `Error: ${data.message}`;
                    nextMessage.status = '';
                  }

                  return nextMessage;
                }));

              } catch (e) {
                console.error("Failed to parse SSE JSON chunk:", jsonStr, e);
              }
            }
          }
        }
      }
    } catch (err) {
      setMessages(prev => prev.map(m => m.id === asstMsgId ? { ...m, content: `Error: ${err.message}`, status: '' } : m));
    } finally {
      setIsLoading(false);
    }
  }

  // Component for rendering an accordion source
  const SourceAccordion = ({ source, extraction }) => {
    const [open, setOpen] = useState(false);
    return (
      <div className="source-accordion">
        <div className="source-header" onClick={() => setOpen(!open)}>
          <span className="source-toggle">{open ? '▼' : '▶'}</span>
          <span className="source-title">{source.video} - {source.chapter.replace(/^chapter_\d+_/, '').replace(/_/g, ' ')}</span>
        </div>
        {open && (
          <div className="source-content">
            {extraction ? (
              <pre className="source-extraction-pre">{extraction.trim()}</pre>
            ) : (
              <span className="source-loading">Extracting context...</span>
            )}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="panel chat-panel">
      <div className="card-header">
        <div>
          <div className="card-title">Chat Assistant</div>
          <div className="card-subtitle">Ask questions or use RAG to query your library</div>
        </div>
      </div>

      <div className="chat-container">
        <div className="chat-messages">
          {messages.length === 0 && (
            <div className="chat-empty">
              <div className="empty-state-icon">💬</div>
              <div className="empty-state-title">Start a conversation</div>
              <div className="empty-state-text">Toggle RAG to search through your processed videos.</div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={m.id || i} className={`chat-message ${m.role === 'user' ? 'message-user' : 'message-assistant'}`}>
              <div className="message-content-wrapper">
                {m.role === 'assistant' ? (
                  m.content ? (
                    <div className="message-content message-markdown">
                      <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]} components={markdownComponents}>
                        {m.content}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    !m.status && <span className="typing-cursor"></span>
                  )
                ) : (
                  <div className="message-content message-plain">{m.content}</div>
                )}
                
                {m.status && (
                  <div className="message-status">
                    <span className="spinner small"></span> {m.status}
                  </div>
                )}

                {m.sources && m.sources.length > 0 && (
                  <div className="message-sources">
                    <div className="message-sources-title">Sources ({m.sources.length}):</div>
                    {m.sources.map(src => (
                      <SourceAccordion 
                        key={src.id} 
                        source={src} 
                        extraction={m.extractions && m.extractions[src.id]} 
                      />
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        <form onSubmit={handleSend} className="chat-input-area">
          <div className="chat-controls">
            <label className="chat-rag-toggle">
              <input 
                type="checkbox" 
                checked={useRag} 
                onChange={e => setUseRag(e.target.checked)} 
                disabled={isLoading}
              />
              <span>Use RAG (Query Library)</span>
            </label>
          </div>
          <div className="chat-input-row">
            <input
              type="text"
              className="chat-input"
              value={input}
              onChange={e => setInput(e.target.value)}
              placeholder={useRag ? "Ask a question about your videos..." : "Chat with Mistral..."}
              disabled={isLoading}
            />
            <button type="submit" className="btn btn-primary" disabled={isLoading || !input.trim()}>
              {isLoading ? 'Thinking...' : 'Send'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}