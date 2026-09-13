import { HomeAssistant } from 'custom-card-helpers';
import { AppleMusicSource, LibraryFilter, SearchConfig, SearchMediaType, SearchResultItem } from '../sections/search/search.types';

const APPLE_MUSIC_SERVICE_ID = '204';
const APPLE_MUSIC_FLAGS = '8224';
const DEFAULT_COUNTRY = 'DE';
const DEFAULT_ACCOUNT_SN = '5';

type ItunesEntity = 'song';

interface ItunesSearchTrack {
  wrapperType?: string;
  kind?: string;
  trackId?: number;
  trackName?: string;
  artistName?: string;
  collectionName?: string;
  artworkUrl100?: string;
  trackViewUrl?: string;
}

interface ItunesSearchResponse {
  resultCount: number;
  results: ItunesSearchTrack[];
}

interface AppleMusicBackendItem {
  title: string;
  artist?: string;
  album?: string;
  track_id?: string;
  media_content_id: string;
  media_content_type?: string;
  thumbnail?: string;
  provider?: string;
  source?: AppleMusicSource;
  didl?: string;
}

interface AppleMusicBackendResponse {
  items: AppleMusicBackendItem[];
}

export class AppleMusicService {
  constructor(private hass?: HomeAssistant) {}

  async search(
    searchText: string,
    mediaTypes: Set<SearchMediaType>,
    searchLimit: number,
    config: SearchConfig,
    libraryFilter: LibraryFilter = 'all',
  ): Promise<SearchResultItem[]> {
    const typesToSearch = mediaTypes.size > 0 ? Array.from(mediaTypes) : ['track'];
    if (!typesToSearch.includes('track')) {
      return [];
    }

    const source = this.resolveSource(config.appleMusicSource ?? 'catalog', libraryFilter);
    if (source === 'library') {
      return this.searchHomeAssistant(searchText, searchLimit, config, 'library');
    }
    if (source === 'all') {
      return this.searchHomeAssistant(searchText, searchLimit, config, 'all');
    }
    if (this.hass?.fetchWithAuth) {
      return this.searchHomeAssistant(searchText, searchLimit, config, 'catalog').catch(() => this.searchCatalog(searchText, searchLimit, config));
    }
    return this.searchCatalog(searchText, searchLimit, config);
  }

  private async searchCatalog(searchText: string, searchLimit: number, config: SearchConfig): Promise<SearchResultItem[]> {
    const response = await fetch(this.buildSearchUrl(searchText, searchLimit, config, 'song'));
    if (!response.ok) {
      throw new Error(`Apple Music search returned ${response.status}`);
    }

    const data = (await response.json()) as ItunesSearchResponse;
    const accountSn = `${config.appleMusicAccountSn ?? DEFAULT_ACCOUNT_SN}`;

    return data.results
      .filter((item) => item.wrapperType === 'track' && item.kind === 'song' && item.trackId && item.trackName)
      .map((item) => ({
        title: item.trackName!,
        subtitle: [item.artistName, item.collectionName].filter(Boolean).join(' - '),
        uri: this.buildSonosTrackUri(item.trackId!, accountSn),
        mediaType: 'track',
        imageUrl: this.upscaleArtwork(item.artworkUrl100),
        artist: item.artistName,
        album: item.collectionName,
        itemId: `${item.trackId}`,
        provider: 'apple_music',
      }));
  }

  private async searchHomeAssistant(searchText: string, searchLimit: number, config: SearchConfig, source: AppleMusicSource): Promise<SearchResultItem[]> {
    if (!this.hass?.fetchWithAuth) {
      throw new Error('Home Assistant Apple Music backend is unavailable');
    }
    const params = new URLSearchParams({
      query: searchText.trim(),
      limit: `${searchLimit}`,
      country: config.appleMusicCountry ?? DEFAULT_COUNTRY,
      account_sn: `${config.appleMusicAccountSn ?? DEFAULT_ACCOUNT_SN}`,
      source,
    });
    const response = await this.hass.fetchWithAuth(`/api/sonos_apple_music/search?${params.toString()}`);
    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || `Home Assistant Apple Music search returned ${response.status}`);
    }
    const data = (await response.json()) as AppleMusicBackendResponse;
    return data.items.map((item) => ({
      title: item.title,
      subtitle: [item.artist, item.album].filter(Boolean).join(' - '),
      uri: item.media_content_id,
      mediaType: 'track',
      imageUrl: item.thumbnail,
      artist: item.artist,
      album: item.album,
      itemId: item.track_id,
      provider: item.provider ?? 'apple_music',
      inLibrary: item.source === 'library',
      didl: item.didl,
    }));
  }

  private resolveSource(configuredSource: AppleMusicSource, libraryFilter: LibraryFilter): AppleMusicSource {
    if (libraryFilter === 'library') {
      return 'library';
    }
    if (libraryFilter === 'non-library') {
      return 'catalog';
    }
    return configuredSource;
  }

  private buildSearchUrl(searchText: string, searchLimit: number, config: SearchConfig, entity: ItunesEntity) {
    const params = new URLSearchParams({
      term: searchText.trim(),
      media: 'music',
      entity,
      limit: `${searchLimit}`,
      country: config.appleMusicCountry ?? DEFAULT_COUNTRY,
    });
    return `https://itunes.apple.com/search?${params.toString()}`;
  }

  private buildSonosTrackUri(trackId: number, accountSn: string) {
    return `x-sonos-http:song%3a${trackId}.mp4?sid=${APPLE_MUSIC_SERVICE_ID}&flags=${APPLE_MUSIC_FLAGS}&sn=${accountSn}`;
  }

  private upscaleArtwork(url?: string) {
    return url?.replace(/100x100bb\.(jpg|png|webp)$/, '600x600bb.$1');
  }
}
