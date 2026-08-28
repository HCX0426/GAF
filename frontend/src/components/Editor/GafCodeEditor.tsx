/**
 * code editor component
 * code editor wrapper based on Monaco Editor, supports multi-language syntax highlighting
 */
import Editor, { type EditorProps } from '@monaco-editor/react';
import type { editor } from 'monaco-editor';

/** GafCodeEditor component props */
interface GafCodeEditorProps {
  value: string;
  language?: string;
  readOnly?: boolean;
  height?: string | number;
  width?: string | number;
  onChange?: (value: string | undefined) => void;
  onMount?: (editor: editor.IStandaloneCodeEditor) => void;
  theme?: string;
  options?: editor.IStandaloneEditorConstructionOptions;
}

/**
 * Monaco Editor wrapper component
 * provides unified code edit experience
 */
export function GafCodeEditor({
  value,
  language = 'python',
  readOnly = false,
  height = '400px',
  width = '100%',
  onChange,
  onMount,
  theme = 'vs-dark',
  options,
}: GafCodeEditorProps) {
  const mergedOptions: EditorProps['options'] = {
    readOnly,
    minimap: { enabled: false },
    fontSize: 14,
    lineNumbers: 'on',
    scrollBeyondLastLine: false,
    automaticLayout: true,
    tabSize: 4,
    ...options,
  };

  return (
    <div style={{ border: '1px solid #d9d9d9', borderRadius: 4, overflow: 'hidden' }}>
      <Editor
        height={height}
        width={width}
        language={language}
        value={value}
        theme={theme}
        onChange={onChange}
        onMount={onMount}
        options={mergedOptions}
      />
    </div>
  );
}

export default GafCodeEditor;
