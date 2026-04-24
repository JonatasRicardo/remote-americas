import js from '@eslint/js';
import parser from '@typescript-eslint/parser';
import plugin from '@typescript-eslint/eslint-plugin';
import eslintConfigPrettier from 'eslint-config-prettier';

export default [
  {
    ignores: ['dist/**', 'reports/**', 'artifacts/**', 'node_modules/**']
  },
  js.configs.recommended,
  {
    files: ['**/*.ts'],
    languageOptions: {
      parser,
      parserOptions: {
        ecmaVersion: 'latest',
        sourceType: 'module'
      }
    },
    plugins: {
      '@typescript-eslint': plugin
    },
    rules: {
      ...plugin.configs.recommended.rules,
      '@typescript-eslint/consistent-type-imports': 'error'
    }
  },
  eslintConfigPrettier
];
