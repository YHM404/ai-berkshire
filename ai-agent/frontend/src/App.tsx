import {
  DeleteOutlined,
  FileTextOutlined,
  FolderAddOutlined,
  FolderOpenOutlined,
  LinkOutlined,
  MessageOutlined,
  MoreOutlined,
  PlusOutlined,
  SearchOutlined,
  StopOutlined,
} from '@ant-design/icons';
import {
  App as AntApp,
  Button,
  Checkbox,
  ConfigProvider,
  Dropdown,
  Empty,
  Form,
  Input,
  Layout,
  List,
  Modal,
  Spin,
  Tag,
  Typography,
  theme,
} from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { api } from './api';
import type { ChatMessage, Project, SessionDetail, SourceItem } from './types';
import './styles.css';

const { Header, Sider, Content } = Layout;
const { Text, Title, Paragraph } = Typography;

type ModalMode = 'project' | 'research' | 'url' | 'note' | null;

function MarkdownContent({ content }: { content: string }) {
  return <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>;
}

function sourceIcon(kind: SourceItem['kind']) {
  if (kind === 'research') return <SearchOutlined />;
  if (kind === 'url') return <LinkOutlined />;
  return <FileTextOutlined />;
}

function sourceTag(source: SourceItem) {
  if (source.status === 'running') return <Tag color="processing">运行中</Tag>;
  if (source.status === 'cancelling') return <Tag color="warning">取消中</Tag>;
  if (source.status === 'failed') return <Tag color="error">失败</Tag>;
  if (source.status === 'cancelled') return <Tag color="default">已取消</Tag>;
  if (source.kind === 'research') return <Tag color="blue">调研</Tag>;
  if (source.kind === 'url') return <Tag color="cyan">网页</Tag>;
  return <Tag color="green">文本</Tag>;
}

function AppShell() {
  const { message } = AntApp.useApp();
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<number | null>(null);
  const [expandedProjectId, setExpandedProjectId] = useState<number | null>(null);
  const [checkedKeys, setCheckedKeys] = useState<string[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [modalMode, setModalMode] = useState<ModalMode>(null);
  const [modalProject, setModalProject] = useState<Project | null>(null);
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [form] = Form.useForm();

  const activeProject = useMemo(
    () => projects.find((p) => p.id === activeProjectId) ?? null,
    [projects, activeProjectId],
  );

  const refresh = useCallback(async () => {
    const data = await api.listProjects();
    setProjects(data);
    setActiveProjectId((current) => {
      if (current && data.some((p) => p.id === current)) return current;
      return data[0]?.id ?? null;
    });
    setExpandedProjectId((current) => {
      if (current && data.some((p) => p.id === current)) return current;
      return data[0]?.id ?? null;
    });
  }, []);

  useEffect(() => {
    refresh().catch((err) => message.error(err.message));
  }, [message, refresh]);

  useEffect(() => {
    const hasActive = projects.some((p) =>
      p.sources.some((s) => s.status === 'running' || s.status === 'cancelling'),
    );
    if (!hasActive) return;
    const timer = window.setInterval(() => {
      refresh().catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [projects, refresh]);

  function selectProject(projectId: number) {
    if (projectId !== activeProjectId) {
      setCheckedKeys([]);
      setMessages([]);
    }
    setActiveProjectId(projectId);
    setExpandedProjectId((current) => (current === projectId ? null : projectId));
  }

  function openModal(mode: ModalMode, project?: Project) {
    setModalMode(mode);
    setModalProject(project ?? null);
    form.resetFields();
  }

  async function submitModal() {
    const values = await form.validateFields();
    if (modalMode === 'project') {
      const project = await api.createProject(values.name);
      await refresh();
      setActiveProjectId(project.id);
      setExpandedProjectId(project.id);
    } else if (modalMode === 'research' && modalProject) {
      await api.startResearch(modalProject.id, values.query);
      setActiveProjectId(modalProject.id);
      setExpandedProjectId(modalProject.id);
      await refresh();
    } else if (modalMode === 'url' && modalProject) {
      await api.addUrl(modalProject.id, values.url);
      await refresh();
    } else if (modalMode === 'note' && modalProject) {
      await api.addNote(modalProject.id, values.title, values.content);
      await refresh();
    }
    setModalMode(null);
  }

  async function deleteProject(project: Project) {
    await api.deleteProject(project.id);
    if (project.id === activeProjectId) {
      setMessages([]);
      setCheckedKeys([]);
    }
    await refresh();
  }

  async function cancelResearch(source: SourceItem) {
    await api.cancelResearch(Number(source.id));
    await refresh();
  }

  async function viewSource(source: SourceItem) {
    const data = source.kind === 'research'
      ? await api.getSession(Number(source.id))
      : await api.getSourceDetail(activeProject!.id, source.kind, source.id);
    setDetail(data);
    setDetailOpen(true);
  }

  async function deleteSource(source: SourceItem) {
    if (!activeProject) return;
    await api.deleteSource(activeProject.id, source.kind, source.id);
    setCheckedKeys((keys) => keys.filter((k) => k !== source.key));
    await refresh();
  }

  function toggleSource(source: SourceItem, checked: boolean) {
    setCheckedKeys((keys) => checked ? [...new Set([...keys, source.key])] : keys.filter((k) => k !== source.key));
  }

  async function deleteChat(sessionId: number) {
    await api.deleteSession(sessionId);
    await refresh();
  }

  async function restoreChat(sessionId: number) {
    const session = await api.getSession(sessionId);
    const restoredMessages = session.messages ?? [];
    const validSourceKeys = new Set(activeProject?.sources.map((source) => source.key) ?? []);
    const restoredSources = (session.data_sources ?? []).filter((key) => validSourceKeys.has(key));

    setMessages(restoredMessages);
    setCheckedKeys(restoredSources);
    setInput('');
  }

  function resetChat() {
    setMessages([]);
    setInput('');
    message.success('已创建新会话');
  }

  async function sendChat() {
    if (!activeProject) {
      message.warning('请先选择或创建项目');
      return;
    }
    if (!checkedKeys.length) {
      message.warning('请先勾选左侧数据源');
      return;
    }
    const text = input.trim();
    if (!text) return;
    setInput('');
    const nextMessages: ChatMessage[] = [...messages, { role: 'user', content: text }];
    setMessages(nextMessages);
    setLoading(true);
    try {
      const res = await api.chat(activeProject.id, text, checkedKeys, messages);
      setMessages([...nextMessages, { role: 'assistant', content: res.answer }]);
      await refresh();
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  const modalTitle = {
    project: '新建项目',
    research: '新建调研',
    url: '添加网页数据源',
    note: '添加文本数据源',
  }[modalMode ?? 'project'];

  return (
    <Layout className="app-layout">
      <Sider width={360} className="sidebar">
        <div className="sidebar-header">
          <div>
            <Text className="eyebrow">AI Berkshire</Text>
            <Title level={4}>项目</Title>
          </div>
          <Button type="primary" icon={<FolderAddOutlined />} onClick={() => openModal('project')}>
            新建
          </Button>
        </div>

        <div className="project-list">
          {projects.length === 0 && <Empty description="暂无项目" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
          {projects.map((project) => {
            const expanded = expandedProjectId === project.id;
            const current = activeProjectId === project.id;
            const running = project.sources.filter((s) => s.status === 'running' || s.status === 'cancelling');
            const available = project.sources.filter((s) => s.status === 'completed' || s.status === 'ready');
            const history = project.sources.filter((s) => s.status === 'failed' || s.status === 'cancelled');
            return (
              <div key={project.id} className={`project-card ${current ? 'active' : ''}`}>
                <div className="project-main" onClick={() => selectProject(project.id)}>
                  <FolderOpenOutlined />
                  <div className="project-title-block">
                    <Text strong>{project.name}</Text>
                    <Text type="secondary">{project.session_count} 条记录</Text>
                  </div>
                </div>
                <Dropdown
                  trigger={['click']}
                  menu={{
                    items: [
                      { key: 'research', icon: <SearchOutlined />, label: '新建调研' },
                      { key: 'url', icon: <LinkOutlined />, label: '添加网页' },
                      { key: 'note', icon: <FileTextOutlined />, label: '添加文本' },
                      { type: 'divider' },
                      { key: 'delete', icon: <DeleteOutlined />, danger: true, label: '删除项目' },
                    ],
                    onClick: ({ key }) => {
                      if (key === 'delete') {
                        Modal.confirm({ title: `删除「${project.name}」？`, okType: 'danger', onOk: () => deleteProject(project) });
                      } else {
                        openModal(key as ModalMode, project);
                        setActiveProjectId(project.id);
                        setExpandedProjectId(project.id);
                      }
                    },
                  }}
                >
                  <Button type="text" icon={<MoreOutlined />} />
                </Dropdown>

                {expanded && (
                  <div className="project-body">
                    {running.map((source) => (
                      <div key={source.key} className="running-row">
                        <Spin size="small" />
                        <Text ellipsis>{source.title}</Text>
                        <Button size="small" icon={<StopOutlined />} onClick={() => cancelResearch(source)}>
                          取消
                        </Button>
                      </div>
                    ))}

                    {available.length > 0 ? (
                      <div className="source-list">
                        {available.map((source) => (
                          <div key={source.key} className="source-list-row">
                            <Checkbox
                              checked={checkedKeys.includes(source.key)}
                              onChange={(e) => toggleSource(source, e.target.checked)}
                            />
                            <button className="source-open" onClick={() => viewSource(source)}>
                              <span className="source-kind-icon">{sourceIcon(source.kind)}</span>
                              <span className="source-title">{source.title}</span>
                              {sourceTag(source)}
                            </button>
                            <Button
                              size="small"
                              type="text"
                              danger
                              icon={<DeleteOutlined />}
                              onClick={() => deleteSource(source)}
                            />
                          </div>
                        ))}
                      </div>
                    ) : running.length === 0 ? (
                      <Empty description="暂无数据源" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                    ) : null}

                    {history.length > 0 && (
                      <div className="history-status">
                        {history.map((source) => <Tag key={source.key}>{source.title} · {source.status}</Tag>)}
                      </div>
                    )}

                    {project.chats.length > 0 && (
                      <div className="chat-history">
                        <Text type="secondary">对话</Text>
                        {project.chats.map((chat) => (
                          <div key={chat.id} className="chat-history-row">
                            <Button type="link" icon={<MessageOutlined />} onClick={() => restoreChat(chat.id)}>
                              {chat.query.slice(0, 18)}
                            </Button>
                            <Button size="small" type="text" danger icon={<DeleteOutlined />} onClick={() => deleteChat(chat.id)} />
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </Sider>

      <Layout>
        <Header className="topbar">
          <Title level={3}>AI Berkshire Agent</Title>
          <div className="topbar-actions">
            {activeProject ? <Tag color="blue">当前项目：{activeProject.name}</Tag> : <Tag>请选择项目</Tag>}
            <Button icon={<PlusOutlined />} disabled={!activeProject} onClick={resetChat}>
              新会话
            </Button>
          </div>
        </Header>
        <Content className="content">
          {!activeProject ? (
            <Empty description="请选择项目或创建新项目" />
          ) : (
            <div className="chat-panel">
              <List
                className="message-list"
                dataSource={messages}
                locale={{ emptyText: '勾选左侧数据源后开始提问' }}
                renderItem={(item) => (
                  <List.Item className={`message-item ${item.role}`}>
                    <div className="message-bubble">
                      <Text strong>{item.role === 'user' ? '你' : 'AI'}</Text>
                      <Paragraph>{item.content}</Paragraph>
                    </div>
                  </List.Item>
                )}
              />
              <div className="composer">
                <Input.TextArea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onPressEnter={(e) => {
                    if (!e.shiftKey) {
                      e.preventDefault();
                      sendChat();
                    }
                  }}
                  autoSize={{ minRows: 2, maxRows: 5 }}
                  placeholder="基于左侧勾选的数据源提问..."
                />
                <Button type="primary" loading={loading} onClick={sendChat}>发送</Button>
              </div>
            </div>
          )}
        </Content>
      </Layout>

      <Modal title={modalTitle} open={modalMode !== null} onOk={submitModal} onCancel={() => setModalMode(null)} destroyOnHidden>
        <Form form={form} layout="vertical">
          {modalMode === 'project' && <Form.Item name="name" label="项目名" rules={[{ required: true }]}><Input /></Form.Item>}
          {modalMode === 'research' && <Form.Item name="query" label="研究问题" rules={[{ required: true }]}><Input.TextArea rows={4} /></Form.Item>}
          {modalMode === 'url' && <Form.Item name="url" label="网页地址" rules={[{ required: true }]}><Input /></Form.Item>}
          {modalMode === 'note' && (
            <>
              <Form.Item name="title" label="标题" rules={[{ required: true }]}><Input /></Form.Item>
              <Form.Item name="content" label="内容" rules={[{ required: true }]}><Input.TextArea rows={6} /></Form.Item>
            </>
          )}
        </Form>
      </Modal>

      <Modal title={detail?.query ?? detail?.title ?? '详情'} open={detailOpen} footer={null} onCancel={() => setDetailOpen(false)} width={900}>
        <div className="detail-content markdown-body">
          {detail?.messages?.map((msg, idx) => (
            <div key={idx} className="detail-message">
              <Text strong>{msg.role}: </Text>
              <MarkdownContent content={msg.content} />
            </div>
          ))}
          {detail?.report_md && <MarkdownContent content={detail.report_md} />}
          {detail?.content && <MarkdownContent content={detail.content} />}
        </div>
      </Modal>
    </Layout>
  );
}

export default function App() {
  return (
    <ConfigProvider theme={{ algorithm: theme.darkAlgorithm, token: { colorPrimary: '#3b82f6', borderRadius: 12 } }}>
      <AntApp>
        <AppShell />
      </AntApp>
    </ConfigProvider>
  );
}
