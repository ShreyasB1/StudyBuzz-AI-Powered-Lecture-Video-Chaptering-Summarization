import React from 'react';

export default function Navbar({ tabs, activeTab, onTabChange }) {
  return (
    <nav className="navbar">
      <div className="navbar-inner">
        <div className="navbar-brand">
          <div className="brand-icon">SB</div>
          <span>StudyBuzz</span>
        </div>
        <ul className="navbar-tabs">
          {tabs.map((tab) => (
            <li
              key={tab.id}
              className={`navbar-tab${activeTab === tab.id ? ' active' : ''}`}
              onClick={() => onTabChange(tab.id)}
            >
              {tab.label}
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
}
