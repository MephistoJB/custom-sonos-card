import { OperationProgress } from '../../types';
import type { MusicAssistantService } from '../../services/music-assistant-service';
import type { AppleMusicService } from '../../services/apple-music-service';
import type { PlayMenuAction } from '../../types';

export type SearchMediaType = 'artist' | 'album' | 'track' | 'playlist' | 'radio';

export type LibraryFilter = 'all' | 'library' | 'non-library';
export type AppleMusicSource = 'catalog' | 'library' | 'all';

export type SearchViewMode = 'list' | 'grid';

export interface HeaderIcon {
  type: SearchMediaType | 'library-filter';
  icon: string;
  title: string;
}

export interface SearchConfig {
  massConfigEntryId?: string;
  appleMusicAccountSn?: string | number;
  appleMusicCountry?: string;
  appleMusicSource?: AppleMusicSource;
  appleMusicAuthBaseUrl?: string;
  defaultMediaType?: SearchMediaType;
  searchLimit?: number;
  title?: string;
  hideActivePlayerName?: boolean;
  autoSearchMinChars?: number;
  autoSearchDebounceMs?: number;
  defaultViewMode?: SearchViewMode;
  gridColumns?: number;
}

export interface MusicAssistantSearchResult {
  media_type: string;
  name: string;
  uri: string;
  version?: string;
  favorite?: boolean;
  in_library?: boolean;
  image?:
    | string
    | {
        path?: string;
        provider?: string;
        remotely_accessible?: boolean;
      };
  artists?: Array<{
    name: string;
    item_id: string;
  }>;
  album?: {
    name: string;
    item_id: string;
  };
  sort_name?: string;
  item_id: string;
  provider: string;
  provider_mappings?: Array<{
    item_id: string;
    provider_domain: string;
    provider_instance: string;
    url?: string;
  }>;
}

export interface MusicAssistantSearchResponse {
  artists?: MusicAssistantSearchResult[];
  albums?: MusicAssistantSearchResult[];
  tracks?: MusicAssistantSearchResult[];
  playlists?: MusicAssistantSearchResult[];
  radio?: MusicAssistantSearchResult[];
}

export interface SearchResultItem {
  title: string;
  subtitle?: string;
  uri: string;
  mediaType: SearchMediaType;
  imageUrl?: string;
  artist?: string;
  album?: string;
  favorite?: boolean;
  inLibrary?: boolean;
  itemId?: string;
  provider?: string;
  didl?: string;
}

export interface SearchExecutionState {
  results: SearchResultItem[];
  loading: boolean;
  error: string | null;
}

export interface SearchHost {
  musicAssistantService: MusicAssistantService;
  appleMusicService: AppleMusicService;
  entityPlatform?: string;
  massConfigEntryId: string;
  results: SearchResultItem[];
  loading: boolean;
  error: string | null;
}

export interface SearchState {
  mediaTypes?: SearchMediaType[];
  searchText: string;
  libraryFilter?: LibraryFilter;
  viewMode?: SearchViewMode;
}

export interface BatchCallbacks {
  setProgress: (p: OperationProgress | null) => void;
  shouldCancel: () => boolean;
  onComplete: () => void;
}

export type SearchFilterAction = { type: 'toggle-media-type'; mediaType: SearchMediaType } | { type: 'toggle-library-filter' } | { type: 'close' };

export type SearchHeaderAction =
  | { type: 'toggle-media-type'; mediaType: SearchMediaType }
  | { type: 'toggle-select-mode' }
  | { type: 'toggle-library-filter' }
  | { type: 'toggle-view-mode' }
  | { type: 'invert-selection' }
  | { type: 'selection-action'; action: PlayMenuAction };
