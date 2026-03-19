import React from 'react';

export default function StatusMessage({ kind = 'info', children, hidden = false, style }) {
  const className = `status ${kind}${hidden ? ' hidden' : ''}`;
  return (
    <div className={className} style={style}>
      {children}
    </div>
  );
}

