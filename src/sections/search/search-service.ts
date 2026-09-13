import { LibraryFilter, SearchConfig, SearchExecutionState, SearchHost, SearchMediaType } from './search.types';
import { performMassSearch, saveSearchState } from './search-utils';

const APPLE_MUSIC_PLATFORM = 'sonos_apple_music';

export class SearchService {
  private debounceTimer?: ReturnType<typeof setTimeout>;
  private searchRequestId = 0;

  constructor(private host: SearchHost) {}

  private updateHost(state: Partial<SearchExecutionState>) {
    Object.assign(this.host, state);
  }

  dispose() {
    this.searchRequestId += 1;

    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
    }
  }

  scheduleSearch(searchText: string, mediaTypes: Set<SearchMediaType>, libraryFilter: LibraryFilter, config: SearchConfig) {
    saveSearchState(mediaTypes, searchText, libraryFilter);
    this.searchRequestId += 1;
    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
    }
    const { autoSearchMinChars = 2, autoSearchDebounceMs = 1000 } = config;
    if (searchText.trim().length < autoSearchMinChars) {
      this.updateHost({ results: [], loading: false });
      return;
    }
    this.debounceTimer = setTimeout(() => this.execute(searchText, mediaTypes, libraryFilter, config), autoSearchDebounceMs);
  }

  async execute(searchText: string, mediaTypes: Set<SearchMediaType>, libraryFilter: LibraryFilter, config: SearchConfig) {
    if (!searchText.trim() || (this.host.entityPlatform !== APPLE_MUSIC_PLATFORM && !this.host.massConfigEntryId)) {
      return;
    }

    const requestId = ++this.searchRequestId;
    this.updateHost({ loading: true, error: null });
    const { searchLimit = 50 } = config;

    try {
      const results =
        this.host.entityPlatform === APPLE_MUSIC_PLATFORM
          ? await this.host.appleMusicService.search(searchText, mediaTypes, searchLimit, config)
          : await performMassSearch(this.host.musicAssistantService, this.host.massConfigEntryId, searchText, mediaTypes, libraryFilter, searchLimit);

      if (requestId === this.searchRequestId) {
        this.updateHost({ results });
      }
    } catch (e) {
      if (requestId === this.searchRequestId) {
        this.updateHost({ error: `Search failed: ${e instanceof Error ? e.message : 'Unknown error'}`, results: [] });
      }
    } finally {
      if (requestId === this.searchRequestId) {
        this.updateHost({ loading: false });
      }
    }
  }

  clear(mediaTypes: Set<SearchMediaType>, libraryFilter: LibraryFilter) {
    this.dispose();
    this.debounceTimer = undefined;
    this.updateHost({ results: [], loading: false, error: null });
    saveSearchState(mediaTypes, '', libraryFilter);
  }
}
