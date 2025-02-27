import logging
from uuid import uuid4
from elasticsearch import helpers, AsyncElasticsearch
from elasticsearch.exceptions import NotFoundError
from ssl import create_default_context
from tracardi.config import tracardi, ElasticConfig
from tracardi import config
from tracardi.domain.value_object.bulk_insert_result import BulkInsertResult
from tracardi.exceptions.log_handler import log_handler

_singleton = None
logger = logging.getLogger(__name__)
logger.setLevel(tracardi.logging_level)
logger.addHandler(log_handler)


class ElasticClient:

    def __init__(self, **kwargs):
        self._cache = {}
        self._client = AsyncElasticsearch(**kwargs)

    async def close(self):
        await self._client.close()

    async def get(self, index, id):
        # WARNING this method does not work on aliases
        return await self._client.get(index=index, doc_type='_doc', id=id)

    # todo error handling move to service
    async def delete(self, index, id):
        # WARNING this method does not work on aliases
        try:
            return await self._client.delete(index=index, doc_type="_doc", id=id)
        except NotFoundError:
            return None

    async def delete_by_query(self, index, body):
        try:
            return await self._client.delete_by_query(index=index, body=body)
        except NotFoundError:
            return None

    async def reindex(self, source, destination, wait_for_completion=True):
        return await self._client.reindex(body={
            "source": {
                "index": source
            },
            "dest": {
                "index": destination
            },

        }, wait_for_completion=wait_for_completion)

    async def get_mapping(self, index):
        return await self._client.indices.get_mapping(index=index)

    async def exists_index_template(self, name):
        return await self._client.indices.exists_index_template(name)

    async def exists(self, index, id) -> bool:
        # WARNING this method does not work on aliases
        try:
            return await self._client.exists(index=index, doc_type="_doc", id=id)
        except NotFoundError:
            return False

    async def search(self, index, query):
        return await self._client.search(index=index, body=query)

    async def scan(self, index, query):
        _generator = helpers.async_scan(
            self._client,
            query=query,
            index=index,
        )

        async for doc in _generator:
            yield doc

    @property
    def cluster(self):
        return self._client.cluster

    async def insert(self, index, records) -> BulkInsertResult:

        if not isinstance(records, list):
            raise ValueError("Insert expects payload to be list.")

        bulk = []
        ids = []
        for record in records:

            if '_id' in record:
                _id = record['_id']
                del (record['_id'])
            else:
                _id = str(uuid4())
                if 'id' in record and _id != record['id']:
                    record['id'] = _id

            ids.append(_id)
            record = {
                "_index": index,
                "_id": _id,
                "_source": record
            }

            bulk.append(record)

        success, errors = await helpers.async_bulk(self._client, bulk)

        return BulkInsertResult(
            saved=success,
            errors=errors,
            ids=ids
        )

    async def update(self, index, id, record, retry_on_conflict=3):
        return await self._client.update(index, body=record, id=id, retry_on_conflict=retry_on_conflict)

    async def remove_index(self, index):
        return await self._client.indices.delete(index=index)

    async def create_index(self, index, mappings):
        return await self._client.indices.create(index=index, ignore=400, body=mappings)

    async def update_aliases(self, body):
        return await self._client.indices.update_aliases(body=body)

    async def delete_alias(self, index, alias):
        return await self._client.indices.delete_alias(name=alias, index=index)

    async def put_index_template(self, template_name, mappings, params=None):
        return await self._client.indices.put_index_template(name=template_name,
                                                             ignore=400,
                                                             body=mappings,
                                                             params=params)

    async def delete_index_template(self, template_name, params=None):
        return await self._client.indices.delete_index_template(
            name=template_name,
            params=params)

    async def exists_index(self, index):
        return await self._client.indices.exists(index=index)

    async def exists_alias(self, alias, index=None):
        return await self._client.indices.exists_alias(name=alias, index=index)

    async def list_indices(self):
        return await self._client.indices.get("*")

    async def list_aliases(self):
        return await self._client.indices.get_alias(name="*")

    async def clone(self, source_index, destination_index):
        return await self._client.indices.clone(index=source_index, target=destination_index)

    async def refresh(self, index, params=None, headers=None):
        return await self._client.indices.refresh(index=index, params=params, headers=headers)

    async def flush(self, index, params=None, headers=None):
        return await self._client.indices.flush(index=index, params=params, headers=headers)

    async def update_by_query(self, index, query):
        return await self._client.update_by_query(index=index, body=query)

    async def count(self, index, query: dict = None):
        return await self._client.count(index=index, body=query)

    """ Snapshots """

    async def create_snapshot_repository(self, name, repo):
        return await self._client.snapshot.create_repository(repository=name, body=repo)

    async def get_snapshot_repository(self, name):
        return await self._client.snapshot.get_repository(repository=name)

    async def delete_snapshot_repository(self, name):
        return await self._client.snapshot.delete_repository(repository=name)

    async def get_repository_snapshots(self, name):
        return await self._client.snapshot.status(repository=name)

    async def create_snapshot(self, repo, snapshot, body=None, params=None):
        return await self._client.snapshot.create(repo, snapshot, body=body, params=params)

    async def restore_snapshot(self, repo, snapshot, body=None, params=None):
        return await self._client.snapshot.restore(repo, snapshot, body=body, params=params)

    async def delete_snapshot(self, repo, snapshot, params=None):
        return await self._client.snapshot.delete(repo, snapshot, params=params)

    async def get_snapshot(self, repo, snapshot, params=None):
        return await self._client.snapshot.get(repo, snapshot, params=params)

    async def get_snapshot_status(self, repo, snapshot, params=None):
        return await self._client.snapshot.status(repository=repo, snapshot=snapshot, params=params)

    @staticmethod
    def get_elastic_config(elastic_config: ElasticConfig):

        kwargs = {}

        if elastic_config.host:
            kwargs['hosts'] = elastic_config.host
        if elastic_config.scheme:
            kwargs['scheme'] = elastic_config.scheme
        if elastic_config.sniffer_timeout:
            kwargs['sniffer_timeout'] = elastic_config.sniffer_timeout
        if elastic_config.sniff_on_start:
            kwargs['sniff_on_start'] = elastic_config.sniff_on_start
        if elastic_config.sniff_on_connection_fail:
            kwargs['sniff_on_connection_fail'] = elastic_config.sniff_on_connection_fail
        if elastic_config.maxsize:
            kwargs['maxsize'] = elastic_config.maxsize

        if elastic_config.ca_file:
            context = create_default_context(cafile=elastic_config.ca_file)
            kwargs['ssl_context'] = context

        if elastic_config.http_auth_password and elastic_config.http_auth_username:
            kwargs['http_auth'] = (elastic_config.http_auth_username, elastic_config.http_auth_password)

        if elastic_config.cloud_id:
            kwargs['cloud_id'] = elastic_config.cloud_id

        if elastic_config.api_key and elastic_config.api_key_id:
            kwargs['api_key'] = (elastic_config.api_key_id, elastic_config.api_key)

        if elastic_config.http_compress:
            kwargs['http_compress'] = elastic_config.http_compress

        if elastic_config.verify_certs is not None:
            kwargs['verify_certs'] = elastic_config.verify_certs

        return kwargs

    @staticmethod
    def instance():

        global _singleton

        def get_elastic_client():
            kwargs = ElasticClient.get_elastic_config(config.elastic)
            return ElasticClient(**kwargs)

        if _singleton is None:
            _singleton = get_elastic_client()

        return _singleton
