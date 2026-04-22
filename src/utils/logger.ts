export interface LoggerOptions {
  debug?: boolean;
}

export class Logger {
  constructor(private readonly options: LoggerOptions = {}) {}

  info(message: string, meta?: Record<string, unknown>): void {
    this.log('INFO', message, meta);
  }

  debug(message: string, meta?: Record<string, unknown>): void {
    if (!this.options.debug) {
      return;
    }
    this.log('DEBUG', message, meta);
  }

  warn(message: string, meta?: Record<string, unknown>): void {
    this.log('WARN', message, meta);
  }

  private log(level: string, message: string, meta?: Record<string, unknown>): void {
    const payload = meta ? ` ${JSON.stringify(meta)}` : '';
    console.log(`[${level}] ${message}${payload}`);
  }
}
