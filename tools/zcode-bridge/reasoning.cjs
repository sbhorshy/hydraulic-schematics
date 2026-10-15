// Session-only effort selection. Read back the runtime value before model work.
async function configureReasoning(rpc, snapshot, requested, emit) {
  const sessionId = snapshot.session.sessionId;
  const supported = (snapshot.settings?.thoughtLevel?.available || []).map(x => x.value);
  const fail = code => {
    emit({type:'configuration.error',sessionId,payload:{code,requested,
      available:supported.filter(x => ['low','high','max'].includes(x))}});
    throw new Error(code);
  };
  if (requested && requested !== 'inherit') {
    if (!supported.includes(requested)) fail('reasoning_unsupported');
    try {
      await rpc('session/setThoughtLevel',{sessionId,thoughtLevel:requested,persistAsWorkspaceLastUsed:false});
      snapshot = await rpc('session/read',{sessionId,contentProfile:'index'});
    } catch { fail('reasoning_configuration_failed'); }
    if (snapshot.settings?.thoughtLevel?.current !== requested) fail('reasoning_mismatch');
  }
  const effective = snapshot.settings?.thoughtLevel?.current;
  emit({type:'reasoning.selected',sessionId,payload:{requested:requested || 'inherit',effective}});
  return snapshot;
}
module.exports = {configureReasoning};
